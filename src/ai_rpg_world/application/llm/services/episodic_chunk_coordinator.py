"""
チャンク境界で SubjectiveEpisode を保存するアプリケーション層の協調オブジェクト。

観測バッファの drain とスライディングウィンドウへの反映は DefaultPromptBuilder.build
と同順（drain → append_all）で行い、直近出来事と一次情報を揃える。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ai_rpg_world.application.llm.chunk_boundary.rules import (
    decide_chunk_boundary,
    summarize_observation_boundary_hints,
)
from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    ISlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _as_utc(value: datetime) -> datetime:
    """naive datetime を UTC aware として扱い、aware はそのまま返す。

    occurred_at の供給源 (HeartbeatObservationEmitter, escape_game runtime,
    PipelineEventPublisher 等) は本来 tz-aware UTC で統一されているべきだが、
    一つでも naive が混ざると比較演算で TypeError になり chunk write が
    全滅する (第20回実験で 48/50 件失敗を観測)。境界で正規化することで
    将来の regression にも耐える。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _action_entry_identity(entry: ActionResultEntry) -> tuple:
    return (
        entry.occurred_at,
        entry.tool_name or "",
        entry.action_summary,
        entry.argument_fingerprint or "",
    )


class EpisodicChunkCoordinator:
    """チャンク状態・境界判定・ChunkEncodingInput 経由のエピソード保存を担う。"""

    def __init__(
        self,
        observation_buffer: IObservationContextBuffer,
        sliding_window_memory: ISlidingWindowMemory,
        action_result_store: IActionResultStore,
        episodic_episode_store: IEpisodicEpisodeStore,
        chunk_episode_draft_builder: ChunkEpisodeDraftBuilder,
        *,
        recent_observations_limit: int = 20,
        recent_actions_limit: int = 20,
        chunk_subjective_fields_service: EpisodicChunkSubjectiveFieldsService | None = None,
        persona_block_provider: Callable[[PlayerId], str] | None = None,
        episodic_memory_link_service: EpisodicMemoryLinkApplicationService | None = None,
        trace_recorder: Optional[ITraceRecorder] = None,
        trace_recorder_provider: Optional[
            Callable[[], Optional[ITraceRecorder]]
        ] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError("observation_buffer must be IObservationContextBuffer")
        if not isinstance(sliding_window_memory, ISlidingWindowMemory):
            raise TypeError("sliding_window_memory must be ISlidingWindowMemory")
        if not isinstance(action_result_store, IActionResultStore):
            raise TypeError("action_result_store must be IActionResultStore")
        if not isinstance(episodic_episode_store, IEpisodicEpisodeStore):
            raise TypeError("episodic_episode_store must be IEpisodicEpisodeStore")
        if not isinstance(chunk_episode_draft_builder, ChunkEpisodeDraftBuilder):
            raise TypeError("chunk_episode_draft_builder must be ChunkEpisodeDraftBuilder")
        if chunk_subjective_fields_service is not None and not isinstance(
            chunk_subjective_fields_service, EpisodicChunkSubjectiveFieldsService
        ):
            raise TypeError(
                "chunk_subjective_fields_service must be EpisodicChunkSubjectiveFieldsService or None"
            )
        if persona_block_provider is not None and not callable(persona_block_provider):
            raise TypeError("persona_block_provider must be callable or None")
        if episodic_memory_link_service is not None and not isinstance(
            episodic_memory_link_service, EpisodicMemoryLinkApplicationService
        ):
            raise TypeError(
                "episodic_memory_link_service must be EpisodicMemoryLinkApplicationService or None"
            )
        if recent_observations_limit < 0:
            raise ValueError("recent_observations_limit must be 0 or greater")
        if recent_actions_limit < 0:
            raise ValueError("recent_actions_limit must be 0 or greater")
        if trace_recorder is not None and not isinstance(trace_recorder, ITraceRecorder):
            raise TypeError("trace_recorder must be ITraceRecorder or None")
        if trace_recorder_provider is not None and not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable or None")
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")

        self._observation_buffer = observation_buffer
        self._sliding_window_memory = sliding_window_memory
        self._action_result_store = action_result_store
        self._episodic_episode_store = episodic_episode_store
        self._chunk_episode_draft_builder = chunk_episode_draft_builder
        self._chunk_subjective_fields_service = chunk_subjective_fields_service
        self._persona_block_provider = persona_block_provider
        self._recent_observations_limit = recent_observations_limit
        self._recent_actions_limit = recent_actions_limit
        self._chunk_actions: Dict[int, List[ActionResultEntry]] = {}
        self._episodic_memory_link_service = episodic_memory_link_service
        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def _resolve_trace_recorder(self) -> Optional[ITraceRecorder]:
        if self._trace_recorder_provider is not None:
            try:
                return self._trace_recorder_provider()
            except Exception:
                return None
        return self._trace_recorder

    def _emit_chunk_written_trace(
        self,
        player_id: PlayerId,
        episode: Any,
        boundary_reason: str,
        action_count: int,
        observation_count: int,
    ) -> None:
        """``EPISODIC_CHUNK_WRITTEN`` を trace に記録する (失敗は握りつぶす)。"""
        recorder = self._resolve_trace_recorder()
        if recorder is None:
            return
        tick: Optional[int] = None
        if self._current_tick_provider is not None:
            try:
                tick = self._current_tick_provider()
            except Exception:
                tick = None
        # cue 一覧は canonical (axis:value) 文字列に。
        cues_canonical: list[str] = []
        try:
            cues_attr = getattr(episode, "cues", ())
            for c in cues_attr:
                try:
                    cues_canonical.append(c.to_canonical())
                except Exception:
                    continue
        except Exception:
            cues_canonical = []
        recall_text = getattr(episode, "recall_text", "") or ""
        try:
            recorder.record(
                TraceEventKind.EPISODIC_CHUNK_WRITTEN,
                tick=tick,
                player_id=int(player_id.value),
                episode_id=getattr(episode, "episode_id", ""),
                boundary_reason=boundary_reason,
                cues=cues_canonical,
                recall_text_snippet=recall_text[:120],
                action_count=action_count,
                observation_count=observation_count,
            )
        except Exception:
            # trace 失敗で chunk 書き込みパスを止めない
            pass

    def after_action_recorded(
        self,
        player_id: PlayerId,
        *,
        explicit_segment_close: bool = False,
    ) -> None:
        """
        IActionResultStore へ 1 件 append 済みの直後に呼ぶ。

        先に drain→スライディングウィンドウへ反映し、チャンクに最新行動を取り込んで境界判定する。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")

        drained = self._observation_buffer.drain(player_id)
        overflow = self._sliding_window_memory.append_all(player_id, list(drained))

        key = player_id.value
        recent_actions = self._action_result_store.get_recent(
            player_id, self._recent_actions_limit
        )
        if not recent_actions:
            return

        newest = recent_actions[0]
        bucket = self._chunk_actions.setdefault(key, [])
        if not bucket or _action_entry_identity(bucket[-1]) != _action_entry_identity(newest):
            bucket.append(newest)

        if not bucket:
            return

        t0 = min(_as_utc(e.occurred_at) for e in bucket)
        t1 = max(_as_utc(e.occurred_at) for e in bucket)

        window_obs = self._sliding_window_memory.get_recent(
            player_id, self._recent_observations_limit
        )
        obs_slice: List[ObservationEntry] = []
        for o in window_obs:
            if t0 <= _as_utc(o.occurred_at) <= t1:
                obs_slice.append(o)
        obs_slice_sorted = tuple(sorted(obs_slice, key=lambda e: e.occurred_at))

        chunk_actions_sorted = tuple(sorted(bucket, key=lambda e: e.occurred_at))

        encoding_input = build_chunk_encoding_input(
            player_id,
            obs_slice_sorted,
            chunk_actions_sorted,
            observation_overflow_from_window=tuple(overflow),
        )
        hints = summarize_observation_boundary_hints(encoding_input.observations)
        decision = decide_chunk_boundary(
            encoding_input,
            hints=hints,
            explicit_segment_close=explicit_segment_close,
        )
        if not decision.should_close_chunk:
            return

        episode = self._chunk_episode_draft_builder.build(encoding_input)
        if self._chunk_subjective_fields_service is not None:
            persona_block = (
                self._persona_block_provider(player_id)
                if self._persona_block_provider is not None
                else ""
            )
            episode = self._chunk_subjective_fields_service.merge_llm_subjective_fields(
                episode,
                persona_text=persona_block,
                encoding_input=encoding_input,
            )
        self._episodic_episode_store.put(episode)
        if self._episodic_memory_link_service is not None:
            self._episodic_memory_link_service.on_episode_committed(episode)
        # Issue #283 後続: chunk 書き込みを trace に残す
        self._emit_chunk_written_trace(
            player_id=player_id,
            episode=episode,
            boundary_reason=decision.reason.value,
            action_count=len(chunk_actions_sorted),
            observation_count=len(obs_slice_sorted),
        )
        self._chunk_actions[key] = []
