"""
チャンク境界で SubjectiveEpisode を保存するアプリケーション層の協調オブジェクト。

観測バッファの drain とスライディングウィンドウへの反映は DefaultPromptBuilder.build
と同順（drain → append_all）で行い、直近出来事と一次情報を揃える。
"""

from __future__ import annotations

from typing import Dict, List, Optional

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
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


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
        if recent_observations_limit < 0:
            raise ValueError("recent_observations_limit must be 0 or greater")
        if recent_actions_limit < 0:
            raise ValueError("recent_actions_limit must be 0 or greater")

        self._observation_buffer = observation_buffer
        self._sliding_window_memory = sliding_window_memory
        self._action_result_store = action_result_store
        self._episodic_episode_store = episodic_episode_store
        self._chunk_episode_draft_builder = chunk_episode_draft_builder
        self._recent_observations_limit = recent_observations_limit
        self._recent_actions_limit = recent_actions_limit
        self._chunk_actions: Dict[int, List[ActionResultEntry]] = {}

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

        t0 = min(e.occurred_at for e in bucket)
        t1 = max(e.occurred_at for e in bucket)

        window_obs = self._sliding_window_memory.get_recent(
            player_id, self._recent_observations_limit
        )
        obs_slice: List[ObservationEntry] = []
        for o in window_obs:
            if t0 <= o.occurred_at <= t1:
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
        self._episodic_episode_store.put(episode)
        self._chunk_actions[key] = []
