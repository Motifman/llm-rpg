"""
チャンク境界で SubjectiveEpisode を保存するアプリケーション層の協調オブジェクト。

観測バッファの drain とスライディングウィンドウへの反映は DefaultPromptBuilder.build
と同順（drain → append_all）で行い、直近出来事と一次情報を揃える。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.scheduler import (
        IEpisodicSubjectiveCompletionScheduler,
    )
    from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
        BeliefEvidenceTranscriber,
    )
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.being.value_object.being_id import BeingId
    from ai_rpg_world.domain.world.value_object.world_id import WorldId

_logger = logging.getLogger(__name__)

from ai_rpg_world.application.llm.chunk_boundary.rules import (
    decide_chunk_boundary,
    summarize_observation_boundary_hints,
)
from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
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

    occurred_at の供給源 (HeartbeatObservationEmitter, world_runtime runtime,
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
        episodic_episode_store: EpisodicEpisodeRepository,
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
        subjective_completion_scheduler: Optional[
            "IEpisodicSubjectiveCompletionScheduler"
        ] = None,
        being_attachment_resolver: Optional["BeingAttachmentResolver"] = None,
        default_world_id: Optional["WorldId"] = None,
        belief_evidence_transcriber: Optional["BeliefEvidenceTranscriber"] = None,
    ) -> None:
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError("observation_buffer must be IObservationContextBuffer")
        if not isinstance(sliding_window_memory, ISlidingWindowMemory):
            raise TypeError("sliding_window_memory must be ISlidingWindowMemory")
        if not isinstance(action_result_store, IActionResultStore):
            raise TypeError("action_result_store must be IActionResultStore")
        if not isinstance(episodic_episode_store, EpisodicEpisodeRepository):
            raise TypeError("episodic_episode_store must be EpisodicEpisodeRepository")
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
        # Port は Protocol なので isinstance チェックは runtime_checkable に依存。
        # ここではゆるく「callable な submit を持つ」を確認するに留め、誤注入の
        # 早期発見だけする。
        if subjective_completion_scheduler is not None and not (
            hasattr(subjective_completion_scheduler, "submit")
            and callable(getattr(subjective_completion_scheduler, "submit"))
        ):
            raise TypeError(
                "subjective_completion_scheduler must implement submit(...) or be None"
            )
        if (
            subjective_completion_scheduler is not None
            and chunk_subjective_fields_service is not None
        ):
            raise ValueError(
                "chunk_subjective_fields_service と subjective_completion_scheduler "
                "を同時に渡せません。同期実行が必要なら InlineEpisodicSubjectiveScheduler "
                "を scheduler 引数に渡してください。"
            )

        # Phase 3 Step 3e-2: episode_store の dual-path 経路用 Resolver
        from ai_rpg_world.domain.being.service.being_attachment_resolver import (
            BeingAttachmentResolver as _BAR,
        )
        from ai_rpg_world.domain.world.value_object.world_id import (
            WorldId as _WID,
        )

        if being_attachment_resolver is not None and not isinstance(
            being_attachment_resolver, _BAR
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if default_world_id is not None and not isinstance(default_world_id, _WID):
            raise TypeError("default_world_id must be WorldId")

        # U2 (証拠台帳統一設計): 転記は wiring 層が flag を見て注入するかどうか
        # 決める (「配線」と「有効化」の分離)。None なら従来通り何もしない。
        if belief_evidence_transcriber is not None:
            from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
                BeliefEvidenceTranscriber as _BET,
            )

            if not isinstance(belief_evidence_transcriber, _BET):
                raise TypeError(
                    "belief_evidence_transcriber must be BeliefEvidenceTranscriber or None"
                )
        self._belief_evidence_transcriber = belief_evidence_transcriber

        self._observation_buffer = observation_buffer
        self._sliding_window_memory = sliding_window_memory
        self._action_result_store = action_result_store
        self._episodic_episode_store = episodic_episode_store
        self._chunk_episode_draft_builder = chunk_episode_draft_builder
        self._chunk_subjective_fields_service = chunk_subjective_fields_service
        self._subjective_completion_scheduler = subjective_completion_scheduler
        self._persona_block_provider = persona_block_provider
        self._being_attachment_resolver = being_attachment_resolver
        self._default_world_id = default_world_id
        self._recent_observations_limit = recent_observations_limit
        self._recent_actions_limit = recent_actions_limit
        self._chunk_actions: Dict[int, List[ActionResultEntry]] = {}
        # 長走時の保険: decide_chunk_boundary が「もう少し溜めよう」を返し続
        # けた場合、bucket が際限なく肥える silent failure を防ぐためのハード
        # キャップ。境界判定の閾値を上回る規模になったら強制的に chunk を
        # close することで、bucket は必ず最大このサイズで止まる。
        # 50 は recent_actions_limit (=20) の 2.5 倍を目安に余裕を見た値。
        self._chunk_actions_hard_cap = 50
        self._episodic_memory_link_service = episodic_memory_link_service
        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def _resolve_being_id_for_episode(self, episode: SubjectiveEpisode):
        """episode.player_id から being_id を解決する。

        Resolver+WorldId が未注入 / Being 未 provision なら None を返す
        (silent skip は呼び出し側の責務。デバッグ可視性のため warning ログは
        呼び出し側で出す)。``_put_episode`` と evidence 転記 (U2) の両方が
        同じ解決結果を使う。
        """
        if (
            self._being_attachment_resolver is None
            or self._default_world_id is None
        ):
            return None
        from ai_rpg_world.domain.player.value_object.player_id import (
            PlayerId as _PID,
        )

        return self._being_attachment_resolver.resolve_being_id(
            self._default_world_id, _PID(int(episode.player_id))
        )

    def _put_episode(self, episode: SubjectiveEpisode) -> None:
        """episode_store への put を being_id 経路で発行する。

        Phase 3 Step 3e-3: legacy player_id 経路は撤去済。Resolver+WorldId が
        未注入 / Being 未 provision なら silent skip (= turn 副作用なので
        次回 turn で再試行)。デバッグ可視性のため warning ログを 1 回出す。

        U2 レビュー対応: 既存テスト (``test_episode_store_caller_being_id_path.py``)
        が本メソッドを ``ClassName._put_episode(mock_self, ep)`` の形で unbound
        呼び出しし、``mock_self._being_attachment_resolver.resolve_being_id`` を
        直接検証している。共通 helper へ抽出すると mock 越しの呼び出し経路が
        変わってテストが壊れるため、あえて ``_resolve_being_id_for_episode`` とは
        別に解決ロジックをそのまま残す (evidence 転記用の解決は
        ``_resolve_being_id_for_episode`` 側で行う)。
        """
        if (
            self._being_attachment_resolver is None
            or self._default_world_id is None
        ):
            _logger.warning(
                "EpisodicChunkCoordinator skipped episode put: Resolver / WorldId "
                "unresolved (episode_id=%s, player_id=%s)。chunk は捨てられるが "
                "turn は継続。",
                episode.episode_id,
                episode.player_id,
            )
            return
        from ai_rpg_world.domain.player.value_object.player_id import (
            PlayerId as _PID,
        )

        being_id = self._being_attachment_resolver.resolve_being_id(
            self._default_world_id, _PID(int(episode.player_id))
        )
        if being_id is None:
            _logger.warning(
                "EpisodicChunkCoordinator skipped episode put: Being not "
                "provisioned (episode_id=%s, player_id=%s)。",
                episode.episode_id,
                episode.player_id,
            )
            return
        self._episodic_episode_store.put_by_being(being_id, episode)

    def _record_belief_evidence_if_applicable(
        self, episode: SubjectiveEpisode
    ) -> None:
        """U2 (証拠台帳統一設計): 同期 LLM 補完直後に prediction_error を
        evidence 化する。transcriber 未注入 (flag OFF) なら何もしない。

        being_id が解決できないとき (未 provision 等) は evidence も
        積まない。``_put_episode`` が同じ episode を silent skip する
        状況と揃える (= episode 自体が保存されないのに evidence だけ
        別 being に残る、という不整合を避ける)。
        """
        if self._belief_evidence_transcriber is None:
            return
        being_id = self._resolve_being_id_for_episode(episode)
        if being_id is None:
            return
        self._belief_evidence_transcriber.record_if_applicable(being_id, episode)

    def _resolve_trace_recorder(self) -> Optional[ITraceRecorder]:
        if self._trace_recorder_provider is not None:
            try:
                return self._trace_recorder_provider()
            except Exception:
                # provider は通常単純な lambda なので例外は希。DI 化や動的
                # 解決を加えたときに silent に消えるのを防ぐため DEBUG で痕跡を残す。
                _logger.debug(
                    "trace_recorder_provider raised; skipping chunk_written trace",
                    exc_info=True,
                )
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
            # trace 失敗で chunk 書き込みパスを止めない方針を維持しつつ、
            # recorder 側のバグを後追いできるよう DEBUG で痕跡を残す。
            _logger.debug(
                "trace recorder.record raised for EPISODIC_CHUNK_WRITTEN; skipping",
                exc_info=True,
            )

    def after_action_recorded(
        self,
        player_id: PlayerId,
        *,
        explicit_segment_close: bool = False,
    ) -> None:
        """
        IActionResultStore へ 1 件 append 済みの直後に呼ぶ。

        先に drain→スライディングウィンドウへ反映し、チャンクに最新行動を取り込んで境界判定する。

        **不変条件 (drain 順序)**: 本メソッドは ``DefaultPromptBuilder.build`` よりも
        前に呼ばれる前提。両者とも同じ ``observation_buffer.drain(player_id)`` を
        呼ぶが drain は idempotent ではなく「最初に呼んだ側が観測を取り去る」。
        本メソッドが先に呼ばれた場合、prompt_builder.build の drain は空を返すが、
        観測自体は既に sliding_window に入っているので ``get_recent`` 経由で正しく
        prompt に届く。逆順 (prompt_builder 先) になると chunk が観測を見れず
        boundary 判定が常に HOLD になるので注意。world_runtime では
        ``_record_action_result`` 末尾 → ``build_full_prompt`` の順で確実に呼ばれている。
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
        # sort key も _as_utc で正規化する: filter で aware に揃えても直後の
        # sort で raw occurred_at を使うと naive/aware 混在で TypeError になる
        # (Issue #311 後続: #309 の取りこぼし)。
        obs_slice_sorted = tuple(sorted(obs_slice, key=lambda e: _as_utc(e.occurred_at)))

        chunk_actions_sorted = tuple(
            sorted(bucket, key=lambda e: _as_utc(e.occurred_at))
        )

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
        # ハードキャップ: 長走で境界判定が常時 False を返し続けると bucket が
        # 無制限に肥える silent failure になる。bucket が hard_cap を超えたら、
        # boundary 判定の結論を上書きして強制的に close する。
        # bucket は decision の入力に既に反映されているので、ここで close を
        # 強制しても encoding_input の中身は最新の状態。
        if not decision.should_close_chunk and len(bucket) >= self._chunk_actions_hard_cap:
            import logging
            logging.getLogger(__name__).warning(
                "EpisodicChunkCoordinator: forcing chunk close (player_id=%s, "
                "bucket_size=%d >= hard_cap=%d). decide_chunk_boundary returned "
                "should_close_chunk=False for too long.",
                player_id, len(bucket), self._chunk_actions_hard_cap,
            )
        elif not decision.should_close_chunk:
            return

        episode = self._chunk_episode_draft_builder.build(encoding_input)
        # 同期 service 経路 (旧来): merge を inline で実行してから store に書く。
        # subjective_completion_scheduler と排他 (__init__ で検証済み)。
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
            # U2 (証拠台帳統一設計): 同期経路の「chunk 主観補完の完了点」は
            # ここ (merge 直後)。episode.prediction_error が確定した直後に
            # 転記する。非同期経路の対応箇所は
            # episodic_subjective_completion_schedulers.py。
            self._record_belief_evidence_if_applicable(episode)
        # draft (もしくは inline merge 済み) を必ず先に store に書く。
        # scheduler 経路 (新規): draft = PR #305 でテンプレ既定値が埋まった状態
        # なので「LLM 完了前でも recall_text が空にならない」が保証される。
        # ワーカーが merge_llm_subjective_fields を実行して同じ episode_id で
        # store を上書きする (Pattern A: Fire-and-forget + eventual consistency)。
        #
        # Phase 3 Step 3e-2: episode_store も dual-path 化。Resolver+WorldId が
        # 注入されていれば being_id 経路、未注入なら legacy player_id 経路。
        # episode.player_id から being_id を引く。3e-3 で legacy 撤去予定。
        self._put_episode(episode)
        if self._subjective_completion_scheduler is not None:
            persona_block = (
                self._persona_block_provider(player_id)
                if self._persona_block_provider is not None
                else ""
            )
            try:
                self._subjective_completion_scheduler.submit(
                    episode,
                    persona_text=persona_block,
                    encoding_input=encoding_input,
                )
            except Exception:
                # scheduler の submit は本来例外を投げないが、誤実装に備えて。
                # 失敗しても draft (テンプレ埋め済み) は既に store にあるため
                # 致命傷にはならない。
                _logger.warning(
                    "subjective_completion_scheduler.submit raised; "
                    "episode draft is kept as-is",
                    exc_info=True,
                )
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
