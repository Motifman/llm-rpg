"""
チャンク境界で SubjectiveEpisode を保存するアプリケーション層の協調オブジェクト。

観測バッファの drain とスライディングウィンドウへの反映は DefaultPromptBuilder.build
と同順（drain → append_all）で行い、直近出来事と一次情報を揃える。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.scheduler import (
        IEpisodicSubjectiveCompletionScheduler,
    )
    from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
        BeliefEvidenceTranscriber,
    )

_logger = logging.getLogger(__name__)

from ai_rpg_world.application.llm.chunk_boundary.rules import (
    decide_chunk_boundary,
    summarize_observation_boundary_hints,
)
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    SettledMissedExpectation,
    build_chunk_encoding_input,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IShortTermMemory,
)
from ai_rpg_world.application.llm.services._pending_prediction_recording import (
    record_pending_prediction_if_applicable,
)
from ai_rpg_world.application.llm.services._pending_prediction_resolution import (
    resolve_pending_predictions_if_applicable,
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
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.pending_prediction_repository import (
    PendingPredictionRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
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


def _action_entry_identity(entry: ActionResultEntry) -> tuple[Any, ...]:
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
        short_term_memory: IShortTermMemory,
        action_result_store: IActionResultStore,
        episodic_episode_store: EpisodicEpisodeRepository,
        chunk_episode_draft_builder: ChunkEpisodeDraftBuilder,
        *,
        recent_observations_limit: int = 20,
        recent_actions_limit: int = 20,
        chunk_subjective_fields_service: EpisodicChunkSubjectiveFieldsService | None = None,
        persona_block_provider: Callable[[PlayerId], str] | None = None,
        # H-2 (自己言及ループ / 横断レビュー): heard_claims の話者照合に使う
        # 本人名 provider。persona_block_provider と同じ player_id 引きの形。
        # 未指定なら自己言及チェックは縮退し従来通り通す (安全側に落とし過ぎて
        # 伝聞が全滅しないようにする)。
        player_name_provider: Callable[[PlayerId], str] | None = None,
        episodic_memory_link_service: EpisodicMemoryLinkApplicationService | None = None,
        trace_recorder: ITraceRecorder | None = None,
        trace_recorder_provider: Callable[[], ITraceRecorder | None] | None = None,
        current_tick_provider: Callable[[], int | None] | None = None,
        subjective_completion_scheduler: IEpisodicSubjectiveCompletionScheduler | None = None,
        belief_evidence_transcriber: BeliefEvidenceTranscriber | None = None,
        error_gated_boundary_enabled: bool = False,
        pending_prediction_store: PendingPredictionRepository | None = None,
        pending_prediction_enabled: bool = False,
    ) -> None:
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError("observation_buffer must be IObservationContextBuffer")
        if not isinstance(short_term_memory, IShortTermMemory):
            raise TypeError("short_term_memory must be IShortTermMemory")
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
        if player_name_provider is not None and not callable(player_name_provider):
            raise TypeError("player_name_provider must be callable or None")
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
        if not isinstance(error_gated_boundary_enabled, bool):
            raise TypeError("error_gated_boundary_enabled must be bool")
        # U10a (予測誤差統一設計 部品6・pending prediction / default None =
        # flag OFF 相当): flag OFF なら従来通り何もしない (「配線と有効化の
        # 分離」)。
        if pending_prediction_store is not None and not isinstance(
            pending_prediction_store, PendingPredictionRepository
        ):
            raise TypeError(
                "pending_prediction_store must be PendingPredictionRepository or None"
            )
        if not isinstance(pending_prediction_enabled, bool):
            raise TypeError("pending_prediction_enabled must be bool")
        # U8 (予測誤差統一設計 部品2a / default False = flag OFF): True のとき
        # だけ decide_chunk_boundary に誤差ゲート境界条項を評価させる。False
        # (既定) では境界挙動は U8 導入前と完全一致する。
        self._error_gated_boundary_enabled = error_gated_boundary_enabled
        self._pending_prediction_store = pending_prediction_store
        self._pending_prediction_enabled = pending_prediction_enabled
        self._belief_evidence_transcriber = belief_evidence_transcriber

        self._observation_buffer = observation_buffer
        self._short_term_memory = short_term_memory
        self._action_result_store = action_result_store
        self._episodic_episode_store = episodic_episode_store
        self._chunk_episode_draft_builder = chunk_episode_draft_builder
        self._chunk_subjective_fields_service = chunk_subjective_fields_service
        self._subjective_completion_scheduler = subjective_completion_scheduler
        self._persona_block_provider = persona_block_provider
        # H-2 (自己言及ループ / 横断レビュー): heard_claims の話者が本人自身か
        # どうかを判定するための本人名 provider。未指定 (None) なら
        # merge_llm_subjective_fields / scheduler.submit に actor_name=None を
        # 渡し、自己判定を行わない (安全側に倒し過ぎて伝聞が全滅しないようにする)。
        self._player_name_provider = player_name_provider
        self._recent_observations_limit = recent_observations_limit
        self._recent_actions_limit = recent_actions_limit
        self._chunk_actions: dict[int, list[ActionResultEntry]] = {}
        # 外れたで確定した予期を、次に閉じる chunk の主観補完に渡すまで持つ (#1443)。
        # 開いている chunk と同じく run の中だけで持つ。受け取り済みの ID も同じ
        # 寿命で持ち、配り直しで同じ外れを別の chunk に二度渡さない。
        self._settled_misses: dict[BeingId, list[SettledMissedExpectation]] = {}
        self._received_miss_event_ids: set[str] = set()
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

    def note_settled_miss(
        self, being_id: BeingId, missed: SettledMissedExpectation
    ) -> bool:
        """外れたで確定した予期を、次に閉じる chunk の主観補完へ渡すために持つ。

        受け取り済みの出来事の ID なら持たずに False を返す。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(missed, SettledMissedExpectation):
            raise TypeError("missed must be SettledMissedExpectation")
        if missed.event_id in self._received_miss_event_ids:
            return False
        self._received_miss_event_ids.add(missed.event_id)
        self._settled_misses.setdefault(being_id, []).append(missed)
        return True

    def _put_episode(self, episode: SubjectiveEpisode) -> None:
        """episode_store への put を episode.being_id 経路で発行する。"""
        self._episodic_episode_store.put_by_being(episode.being_id, episode)

    def _record_heard_claims_if_applicable(self, episode: SubjectiveEpisode) -> None:
        """P9 (伝聞): 同期 LLM 補完直後に heard_claims を HEARSAY evidence に転記する。

        予測の当否は確定した予期から積む (#1443) ので、ここでは扱わない。
        transcriber 未注入 (flag OFF) なら何もしない。
        """
        if self._belief_evidence_transcriber is None:
            return
        self._belief_evidence_transcriber.record_heard_claims(episode.being_id, episode)

    def _record_pending_prediction_if_applicable(
        self,
        episode: SubjectiveEpisode,
    ) -> None:
        """U10a (予測誤差統一設計 部品6): 抽出された約束・見込みを

        ``PendingPrediction`` 化して per-Being store に積む (共通ロジックは
        ``_pending_prediction_recording.record_pending_prediction_if_applicable``
        に集約。非同期 scheduler 経路の対応箇所も同じ関数を呼ぶ)。
        """
        record_pending_prediction_if_applicable(
            pending_prediction_store=self._pending_prediction_store,
            pending_prediction_enabled=self._pending_prediction_enabled,
            being_id=episode.being_id,
            episode=episode,
            current_tick_provider=self._current_tick_provider,
            trace_recorder=self._resolve_trace_recorder(),
        )

    def _resolve_pending_predictions_if_applicable(
        self,
        episode: SubjectiveEpisode,
    ) -> None:
        """U10b (予測誤差統一設計 部品6・清算): 再浮上していた約束の履行/破棄

        判定を evidence に転記し、決着分と期限切れ分を store から除く (共通
        ロジックは ``_pending_prediction_resolution`` に集約。非同期 scheduler
        経路も同じ関数を呼ぶ)。
        """
        resolve_pending_predictions_if_applicable(
            pending_prediction_store=self._pending_prediction_store,
            pending_prediction_enabled=self._pending_prediction_enabled,
            being_id=episode.being_id,
            episode=episode,
            belief_evidence_transcriber=self._belief_evidence_transcriber,
            current_tick_provider=self._current_tick_provider,
            trace_recorder=self._resolve_trace_recorder(),
        )

    def _active_pending_predictions_for(
        self, being_id: BeingId
    ) -> tuple[Any, ...]:
        """U10b: この chunk の補完時点で「窓が開いた」約束 (tick_from に達した

        もの) を返す。chunk 主観補完 LLM に「果たされたか」を判定させるため
        ``ChunkEncodingInput.active_pending_predictions`` に載せる。

        flag OFF / store 未配線 / being 未解決 / current_tick 不明のときは
        空タプル (= プロンプトに【保留中の約束】節が出ず、導入前と一致)。
        """
        if not self._pending_prediction_enabled or self._pending_prediction_store is None:
            return ()
        if self._current_tick_provider is None:
            return ()
        try:
            current_tick = self._current_tick_provider()
        except Exception:
            return ()
        if not isinstance(current_tick, int) or isinstance(current_tick, bool):
            return ()
        try:
            live = self._pending_prediction_store.list_all_by_being(being_id)
        except Exception:
            return ()
        return tuple(p for p in live if p.tick_from <= current_tick)

    def _resolve_trace_recorder(self) -> ITraceRecorder | None:
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
        settled_miss_event_ids: list[str],
    ) -> None:
        """``EPISODIC_CHUNK_WRITTEN`` を trace に記録する (失敗は握りつぶす)。"""
        recorder = self._resolve_trace_recorder()
        if recorder is None:
            return
        tick: int | None = None
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
                settled_miss_event_ids=settled_miss_event_ids,
            )
        except Exception:
            # trace 失敗で chunk 書き込みパスを止めない方針を維持しつつ、
            # recorder 側のバグを後追いできるよう DEBUG で痕跡を残す。
            _logger.debug(
                "trace recorder.record raised for EPISODIC_CHUNK_WRITTEN; skipping",
                exc_info=True,
            )

    def _emit_prediction_outcome_trace(
        self,
        *,
        player_id: PlayerId,
        episode: SubjectiveEpisode,
        chunk_actions: tuple[ActionResultEntry, ...],
    ) -> None:
        """``PREDICTION_OUTCOME`` を trace に記録する (失敗は握りつぶす)。

        prediction_context_ids は chunk を構成する action 群のうち id が付いて
        いたものの重複排除リスト (U1 では「紐付けの土台」だけを残し、「どの
        belief/episode が in-context だったか」の意味づけは U4 の attribution
        ledger に委ねる)。

        **id 機構が OFF (= 発行された id が 1 つも無い) のときは emit しない**。
        PREDICTION_CONTEXT_ID_ENABLED=OFF (default) では action に id が付かない
        ので、この条件により default run の trace は U1 導入前と完全に一致する
        (共通規約 §0 / §4 の「flag を戻せば挙動が導入前と一致する」規律)。
        prediction_error=None (予測どおり) でも in-context id があれば emit する
        (的中を後段 U4 の CONFIRMATION 転記が拾えるようにするため)。
        """
        prediction_context_ids: list[str] = []
        try:
            for action in chunk_actions:
                pid = getattr(action, "prediction_context_id", None)
                if pid and pid not in prediction_context_ids:
                    prediction_context_ids.append(pid)
        except Exception:
            prediction_context_ids = []
        if not prediction_context_ids:
            return
        recorder = self._resolve_trace_recorder()
        if recorder is None:
            return
        tick: int | None = None
        if self._current_tick_provider is not None:
            try:
                tick = self._current_tick_provider()
            except Exception:
                tick = None
        try:
            recorder.record(
                TraceEventKind.PREDICTION_OUTCOME,
                tick=tick,
                player_id=int(player_id.value),
                episode_id=getattr(episode, "episode_id", ""),
                prediction_error=getattr(episode, "prediction_error", None),
                prediction_context_ids=prediction_context_ids,
            )
        except Exception:
            _logger.debug(
                "trace recorder.record raised for PREDICTION_OUTCOME; skipping",
                exc_info=True,
            )

    def after_action_recorded(
        self,
        player_id: PlayerId,
        being_id: BeingId,
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
        観測自体は既に短期記憶に入っているので ``get_recent`` 経由で正しく
        prompt に届く。逆順 (prompt_builder 先) になると chunk が観測を見れず
        boundary 判定が常に HOLD になるので注意。world_runtime では
        ``_record_action_result`` 末尾 → ``build_full_prompt`` の順で確実に呼ばれている。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")

        drained = self._observation_buffer.drain(player_id)
        overflow = self._short_term_memory.append_all(player_id, list(drained))

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

        window_obs = self._short_term_memory.get_recent(
            player_id, self._recent_observations_limit
        )
        obs_slice: list[ObservationEntry] = []
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
            # U10b: 窓が開いた約束を補完プロンプトに載せて「果たされたか」を
            # 判定させる。flag OFF / 該当なしのときは空 (= 導入前と一致)。
            active_pending_predictions=self._active_pending_predictions_for(being_id),
            settled_missed_expectations=tuple(self._settled_misses.get(being_id, ())),
        )
        hints = summarize_observation_boundary_hints(encoding_input.observations)
        decision = decide_chunk_boundary(
            encoding_input,
            hints=hints,
            explicit_segment_close=explicit_segment_close,
            error_gated_boundary_enabled=self._error_gated_boundary_enabled,
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

        episode = self._chunk_episode_draft_builder.build(
            encoding_input, being_id=being_id
        )
        # 同期 service 経路 (旧来): merge を inline で実行してから store に書く。
        # subjective_completion_scheduler と排他 (__init__ で検証済み)。
        if self._chunk_subjective_fields_service is not None:
            persona_block = (
                self._persona_block_provider(player_id)
                if self._persona_block_provider is not None
                else ""
            )
            # H-2: actor_name は persona_block_provider と同じ player_id 引きの
            # provider から取る。未配線 (None) なら actor_name=None のまま
            # merge に渡し、自己判定を行わない (persona_block と同じ規約)。
            actor_name = (
                self._player_name_provider(player_id)
                if self._player_name_provider is not None
                else None
            )
            episode = self._chunk_subjective_fields_service.merge_llm_subjective_fields(
                episode,
                persona_text=persona_block,
                encoding_input=encoding_input,
                actor_name=actor_name,
            )
            # U1: prediction_error が同期経路で確定した瞬間に PREDICTION_OUTCOME
            # を emit する (非同期 scheduler 経路は完了時に別途 emit する)。
            self._emit_prediction_outcome_trace(
                player_id=player_id,
                episode=episode,
                chunk_actions=encoding_input.action_results,
            )
            self._record_heard_claims_if_applicable(episode)
            # U10a (予測誤差統一設計 部品6・pending prediction): 同じ完了点で
            # 抽出された約束・見込みを PendingPrediction 化して per-Being
            # store に積む。flag OFF / 抽出なし / store 未配線なら no-op
            # (導入前と完全に一致)。
            self._record_pending_prediction_if_applicable(episode)
            # U10b (予測誤差統一設計 部品6・清算): 同じ完了点で、再浮上して
            # いた約束の履行/破棄判定を evidence に転記し、決着分と期限切れ分を
            # store から除く。flag OFF / store 未配線なら no-op。抽出 (U10a) の
            # 後に呼ぶことで「今回の chunk で作られた約束」を同じ完了で
            # 誤って清算しないよう順序を保つ (新規約束は tick_from が未来なので
            # active に載らないが、順序も明示しておく)。
            self._resolve_pending_predictions_if_applicable(episode)
        # draft (もしくは inline merge 済み) を必ず先に store に写す。
        # scheduler 経路 (新規): draft = PR #305 でテンプレ既定値が埋まった状態
        # なので「LLM 完了前でも recall_text が空にならない」が保証される。
        # ワーカーが merge_llm_subjective_fields を実行して同じ episode_id で
        # store を上書きする (Pattern A: Fire-and-forget + eventual consistency)。
        #
        # draft builder が episode.being_id に刻む。store キーと VO の being_id
        # が食い違う書き込みは put で失敗する。
        self._put_episode(episode)
        if self._subjective_completion_scheduler is not None:
            persona_block = (
                self._persona_block_provider(player_id)
                if self._persona_block_provider is not None
                else ""
            )
            # H-2: 非同期経路も同期経路と同じ actor_name 解決規約 (未配線なら None)。
            actor_name = (
                self._player_name_provider(player_id)
                if self._player_name_provider is not None
                else None
            )
            try:
                self._subjective_completion_scheduler.submit(
                    episode,
                    persona_text=persona_block,
                    encoding_input=encoding_input,
                    actor_name=actor_name,
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
            settled_miss_event_ids=[
                m.event_id for m in encoding_input.settled_missed_expectations
            ],
        )
        self._chunk_actions[key] = []
        handed = encoding_input.settled_missed_expectations
        remaining = self._settled_misses.get(being_id, [])[len(handed):]
        if remaining:
            self._settled_misses[being_id] = remaining
        else:
            self._settled_misses.pop(being_id, None)
