"""``InlineEpisodicSubjectiveScheduler`` / ``ThreadPoolEpisodicSubjectiveScheduler``
の単体テスト (PR #309 / Issue #295 後続)。

検証範囲:
- 正常系: submit 完了で store の episode が merged で上書きされる
- 失敗系: LLM 例外を握り込み draft (= 上書き無し) のまま残す
- 重複: 同一 episode_id の submit は 1 回しか走らない (dedupe)
- 満杯: max_queue_size 超過で drop され ``EPISODIC_SUBJECTIVE_DROPPED`` 出る
- shutdown: 進行中ジョブを drain、shutdown 後の submit は静かに drop
- thread safety: ワーカーから put する間、メイン thread の get/list が壊れない
- trace: FILLED / FAILED / DROPPED 3 種の event payload が正しい
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, List

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers import (
    InlineEpisodicSubjectiveScheduler,
    ThreadPoolEpisodicSubjectiveScheduler,
)
from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
    InMemoryPendingPredictionStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.trace import (
    ITraceRecorder,
    NullTraceRecorder,
    TraceEventKind,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _capture(recorder: NullTraceRecorder) -> List:
    captured: List = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


class _StubPort(IEpisodicChunkSubjectiveCompletionPort):
    def __init__(self, *, returns: dict | None = None, raises: BaseException | None = None, delay: float = 0.0):
        self._returns = returns
        self._raises = raises
        self._delay = delay
        self.call_count = 0

    def complete_episode_subjective_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.call_count += 1
        if self._delay:
            time.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        return self._returns or {"interpreted": "I", "recall_text": "R"}


def _build_encoding_and_draft(*, player_id: int = 7) -> tuple:
    """最小限の ChunkEncodingInput + draft Episode + Being 一式を作る。

    Phase 3 Step 3e-3: scheduler は being_id 経路必須となったため、helper で
    Being 解決一式 (being_id / resolver / world_id) も同時に返す。
    返り値: ``(enc, draft, being_id, resolver, world_id)``。
    """
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(
        occurred_at=t,
        action_summary="待機した",
        result_summary="時間が進んだ",
        tool_name="wait",
        success=True,
    )
    enc = build_chunk_encoding_input(PlayerId(player_id), (), (act,))
    draft = ChunkEpisodeDraftBuilder().build(enc)
    being_id, resolver, world_id = _provision_scheduler(player_id)
    return enc, draft, being_id, resolver, world_id


def _build_encoding_and_draft_with_attribution(
    *,
    player_id: int = 7,
    in_context_belief_ids: tuple[str, ...] = (),
    expected_result: str | None = None,
) -> tuple:
    """U4: attribution 計算対象の action に in_context_belief_ids /
    expected_result を乗せた ChunkEncodingInput + draft を作る。"""
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(
        occurred_at=t,
        action_summary="待機した",
        result_summary="時間が進んだ",
        tool_name="wait",
        success=True,
        in_context_belief_ids=in_context_belief_ids,
        expected_result=expected_result,
    )
    enc = build_chunk_encoding_input(PlayerId(player_id), (), (act,))
    draft = ChunkEpisodeDraftBuilder().build(enc)
    being_id, resolver, world_id = _provision_scheduler(player_id)
    return enc, draft, being_id, resolver, world_id


def _build_encoding_and_draft_with_prediction_context_id(
    *,
    player_id: int = 7,
    prediction_context_id: str | None = None,
    expected_result: str | None = None,
) -> tuple:
    """U9a/U9b: 想起の信用割り当ての刻み対象を特定する
    ``prediction_context_id`` を乗せた ChunkEncodingInput + draft を作る。

    U9b (的中側): ``expected_result`` を渡すと「実際に予測を伴う行動が
    あった」扱いになり、``compute_chunk_attribution`` の
    ``had_expected_result`` ガードを満たす。
    """
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(
        occurred_at=t,
        action_summary="待機した",
        result_summary="時間が進んだ",
        tool_name="wait",
        success=True,
        prediction_context_id=prediction_context_id,
        expected_result=expected_result,
    )
    enc = build_chunk_encoding_input(PlayerId(player_id), (), (act,))
    draft = ChunkEpisodeDraftBuilder().build(enc)
    being_id, resolver, world_id = _provision_scheduler(player_id)
    return enc, draft, being_id, resolver, world_id


def _seed_recall_observation(store, being_id, *, prediction_context_id: str) -> None:
    """U9a テスト用: 刻み対象となる pending recall observation を 1 件仕込む。"""
    from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
        EpisodicRecallObservation,
    )

    store.append_by_being(
        being_id,
        EpisodicRecallObservation(
            recall_id="r-1",
            player_id=1,
            episode_id="ep-source",
            recalled_at=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc),
            source_axes=("temporal",),
            current_state_snapshot="state",
            recent_events_snapshot="events",
            persona_snapshot="persona",
            situation_cues=("cue",),
            turn_index=1,
            prediction_context_id=prediction_context_id,
        ),
    )


def _provision_scheduler(player_id: int):
    """Phase 3 Step 3e-3: 各テストで scheduler に Resolver を inject するための
    Being+Resolver+WorldId 一式を組み立てる helper。

    返り値: ``(being_id, resolver, world_id)``。
    """
    from ai_rpg_world.application.being.being_provisioning_service import (
        BeingProvisioningService,
    )
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.world.value_object.world_id import (
        DEFAULT_SINGLE_WORLD_ID,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
        InMemoryBeingRepository,
    )

    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    being_id = BeingProvisioningService(repo).ensure_attached(PlayerId(player_id))
    return being_id, resolver, DEFAULT_SINGLE_WORLD_ID


# ─────────────────────────────────────────────
# InlineEpisodicSubjectiveScheduler
# ─────────────────────────────────────────────


class TestInlineScheduler:
    """同期 scheduler が同じ thread 内で merge → store 上書きを完結させる。"""

    def test_submit_store_episode_llm_overwritten(self) -> None:
        """submit で store の episode が LLM 文に上書きされる。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)  # chunk_coordinator が事前に draft を入れた状態を模す
        port = _StubPort(returns={"interpreted": "STUB_I", "recall_text": "STUB_R"})
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
                    being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="ペルソナ", encoding_input=enc)
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.interpreted == "STUB_I"
        assert ep_after.recall_text == "STUB_R"
        assert port.call_count == 1

    def test_llm_failure_draft_failed_trace(self) -> None:
        """LLM 失敗時は draft のまま FAILED trace を出す。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        # service 自体は例外を呑むのでテンプレで上書きされてしまう。
        # 「FAILED trace を出す」挙動を確認するために scheduler 内部例外を仕込む:
        # service.merge_llm_subjective_fields 自体が呼べないケースを stub する。
        class _BoomService(EpisodicChunkSubjectiveFieldsService):
            def merge_llm_subjective_fields(self, *a, **kw):  # type: ignore[override]
                raise RuntimeError("scheduler-level boom")
        port = _StubPort()
        bad_svc = _BoomService(port)
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(
            bad_svc, store,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 42,
                    being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        assert len(failed) == 1
        assert failed[0].player_id == int(draft.player_id)
        assert failed[0].tick == 42
        assert failed[0].payload["episode_id"] == draft.episode_id
        # store の episode は draft のまま (上書き無し)
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after == draft

    def test_filled_trace_recall_text_snippet_120(self) -> None:
        """FILLED trace の recall text snippet は 120 文字まで。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        long_recall = "あ" * 500
        port = _StubPort(returns={"interpreted": "X", "recall_text": long_recall})
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            trace_recorder_provider=lambda: recorder,
                    being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        filled = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FILLED]
        assert len(filled) == 1
        assert len(filled[0].payload["recall_text_snippet"]) <= 120

    def test_u1_prediction_error_prediction_outcome_id_rendered(
        self,
    ) -> None:
        """chunk を構成する action の prediction_context_id が重複排除で乗り、
        LLM が書いた prediction_error 文字列がそのまま payload に乗る。"""
        t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
        act1 = ActionResultEntry(
            occurred_at=t,
            action_summary="扉を開けた",
            result_summary="鍵がかかっていた",
            tool_name="interact",
            prediction_context_id="predctx-aaa",
        )
        act2 = ActionResultEntry(
            occurred_at=t,
            action_summary="別の扉を開けた",
            result_summary="開いた",
            tool_name="interact",
            prediction_context_id="predctx-aaa",  # 重複 (同じ id が 2 action に乗る想定)
        )
        enc = build_chunk_encoding_input(PlayerId(7), (), (act1, act2))
        draft = ChunkEpisodeDraftBuilder().build(enc)
        being_id, resolver, world_id = _provision_scheduler(7)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "開くと思ったら鍵がかかっていた",
            }
        )
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            trace_recorder_provider=lambda: recorder,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        outcomes = [
            e for e in events if e.kind == TraceEventKind.PREDICTION_OUTCOME
        ]
        assert len(outcomes) == 1
        ev = outcomes[0]
        assert ev.payload["episode_id"] == draft.episode_id
        assert ev.payload["prediction_error"] == "開くと思ったら鍵がかかっていた"
        assert ev.payload["prediction_context_ids"] == ["predctx-aaa"]

    def test_u1_prediction_error_none_context_id_prediction_outcome_rendered(
        self,
    ) -> None:
        """予測どおり (None) でも in-context id があれば「判定は走った」事実を
        残す (的中を後段 U4 の CONFIRMATION 転記が拾えるようにするため)。"""
        t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t,
            action_summary="待機した",
            result_summary="時間が進んだ",
            tool_name="wait",
            prediction_context_id="predctx-bbb",
        )
        enc = build_chunk_encoding_input(PlayerId(7), (), (act,))
        draft = ChunkEpisodeDraftBuilder().build(enc)
        being_id, resolver, world_id = _provision_scheduler(7)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            trace_recorder_provider=lambda: recorder,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        outcomes = [
            e for e in events if e.kind == TraceEventKind.PREDICTION_OUTCOME
        ]
        assert len(outcomes) == 1
        assert outcomes[0].payload["prediction_error"] is None
        assert outcomes[0].payload["prediction_context_ids"] == ["predctx-bbb"]

    def test_u1_id_off_id_prediction_outcome_not_rendered_2(self) -> None:
        """PREDICTION_CONTEXT_ID_ENABLED=OFF (default) では action に id が付かない。
        その場合 PREDICTION_OUTCOME を emit せず、trace が U1 導入前と一致する。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            trace_recorder_provider=lambda: recorder,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        outcomes = [
            e for e in events if e.kind == TraceEventKind.PREDICTION_OUTCOME
        ]
        assert outcomes == []

    def test_shutdown_noop(self) -> None:
        """shutdown は noop。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        port = _StubPort()
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
        ,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.shutdown()  # 例外なく終わる
        scheduler.shutdown(timeout=1.0)  # 何度呼んでも安全


# ─────────────────────────────────────────────
# ThreadPoolEpisodicSubjectiveScheduler
# ─────────────────────────────────────────────


class TestThreadPoolScheduler:
    """非同期 scheduler が裏で merge → store 上書きを完了する。"""

    def test_submit_after_shutdown_store_llm_overwritten(self) -> None:
        """submit 後 shutdown で store が LLM 文に上書きされる。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns={"interpreted": "ASYNC_I", "recall_text": "ASYNC_R"})
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            max_workers=1,
                    being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        try:
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            scheduler.shutdown()  # drain
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.recall_text == "ASYNC_R"
        assert ep_after.interpreted == "ASYNC_I"

    def test_u1_context_id_prediction_outcome_id_rendered(self) -> None:
        """非同期経路でも in-context id 付き chunk では PREDICTION_OUTCOME を emit。"""
        t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t,
            action_summary="待機した",
            result_summary="時間が進んだ",
            tool_name="wait",
            prediction_context_id="predctx-async",
        )
        enc = build_chunk_encoding_input(PlayerId(7), (), (act,))
        draft = ChunkEpisodeDraftBuilder().build(enc)
        being_id, resolver, world_id = _provision_scheduler(7)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            max_workers=1,
            trace_recorder_provider=lambda: recorder,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        try:
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            scheduler.shutdown()
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        outcomes = [
            e for e in events if e.kind == TraceEventKind.PREDICTION_OUTCOME
        ]
        assert len(outcomes) == 1
        assert outcomes[0].payload["prediction_context_ids"] == ["predctx-async"]

    def test_u1_id_off_id_prediction_outcome_not_rendered(self) -> None:
        """非同期経路でも PREDICTION_CONTEXT_ID_ENABLED=OFF (= id 無し) では
        PREDICTION_OUTCOME を emit しない (default run の trace が導入前と一致)。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            max_workers=1,
            trace_recorder_provider=lambda: recorder,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        try:
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            scheduler.shutdown()
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        outcomes = [
            e for e in events if e.kind == TraceEventKind.PREDICTION_OUTCOME
        ]
        assert outcomes == []

    def test_submit_non(self) -> None:
        """重い LLM (1 秒 sleep) を投げても submit は瞬時に返る。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(delay=1.0)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
        ,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        try:
            t0 = time.monotonic()
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            elapsed = time.monotonic() - t0
            assert elapsed < 0.2, f"submit がブロックした: {elapsed:.3f}s"
        finally:
            scheduler.shutdown(timeout=2.0)

    def test_llm_failure_draft_failed_trace_rendered(self) -> None:
        """LLM 失敗時は draft のまま FAILEDtrace が出る。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        # scheduler レベルで失敗するには service 自体に例外を仕込む
        class _BoomService(EpisodicChunkSubjectiveFieldsService):
            def merge_llm_subjective_fields(self, *a, **kw):  # type: ignore[override]
                raise LlmApiCallException("down", error_code="LLM_API_CALL_FAILED")
        port = _StubPort()
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            _BoomService(port), store,
            trace_recorder_provider=lambda: recorder,
                    being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        scheduler.shutdown()
        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        assert len(failed) == 1
        # draft が store に残っている (上書き無し)
        assert store.get_by_being(being_id, draft.episode_id) == draft

    def test_same_episode_id_duplicate_submit_dedupe(self) -> None:
        """同一 episodeid の重複 submit は dedupe される。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        # delay を入れて 2 回目の submit が 1 回目と同時 in-flight になるよう仕組む
        port = _StubPort(delay=0.3)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
        ,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        try:
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            scheduler.shutdown()
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        # 同一 episode_id の重複は 1 回しか LLM を呼ばない
        assert port.call_count == 1

    def test_max_queue_size_exceeds_dropped_trace_rendered(self) -> None:
        """max_queue_size=2 に設定して 3 件投げると 1 件は drop される。"""
        enc1, draft1, being1, resolver, world_id = _build_encoding_and_draft(player_id=1)
        enc2, draft2, being2, _, _ = _build_encoding_and_draft(player_id=2)
        enc3, draft3, being3, _, _ = _build_encoding_and_draft(player_id=3)
        # 各 player ごとに別 Being。代表で player_id=1 の Resolver を scheduler に注入
        # (= 各 player_id を Resolver で解決するとそれぞれ別 Being にぶつかるが、
        # 本テストの主目的は queue 満杯時の DROPPED trace 検出なので Resolver は
        # 1 player 分で足りる。put_by_being は各 Being で行う)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being1, draft1)
        store.put_by_being(being2, draft2)
        store.put_by_being(being3, draft3)
        # 全 worker が詰まるように長めの delay
        port = _StubPort(delay=0.5)
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store,
            max_workers=1,
            max_queue_size=2,
            trace_recorder_provider=lambda: recorder,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        try:
            scheduler.submit(draft1, persona_text="", encoding_input=enc1)
            scheduler.submit(draft2, persona_text="", encoding_input=enc2)
            # 3 件目は queue 満杯で drop される (in-flight 2 件)
            scheduler.submit(draft3, persona_text="", encoding_input=enc3)
        finally:
            scheduler.shutdown(timeout=3.0)
        dropped = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_DROPPED]
        assert len(dropped) == 1
        assert dropped[0].payload["episode_id"] == draft3.episode_id
        assert dropped[0].payload["max_queue_size"] == 2

    def test_shutdown_after_submit_dropped_trace_drop(self) -> None:
        """無音 drop ではなく観測可能にする (silent-failure-hunter #1 への対応)。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort()
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store,
            trace_recorder_provider=lambda: recorder,
                    being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.shutdown()
        # shutdown 後の submit は例外を上げない
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        # LLM も呼ばれない
        assert port.call_count == 0
        # DROPPED trace が「shutdown 由来」と分かる形で記録されている
        dropped = [
            e for e in events
            if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_DROPPED
        ]
        assert len(dropped) == 1
        assert dropped[0].payload["episode_id"] == draft.episode_id
        assert dropped[0].payload["reason"] == "shutdown"

    def test_shutdown_timeout(self) -> None:
        """shutdowntimeout で未完了は諦める。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        # 5 秒寝るので 0.1 秒 timeout では完了しない
        port = _StubPort(delay=5.0)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
        ,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        t0 = time.monotonic()
        scheduler.shutdown(timeout=0.1)
        elapsed = time.monotonic() - t0
        # timeout を大きく超えて待たない (= ジョブを諦めて返る)
        assert elapsed < 1.5, f"shutdown が長すぎる: {elapsed:.2f}s"

    def test_shutdown_timeout_warn_log_observation(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """timeout 超過ジョブは episode_id 付きで WARN ログに出る
        (silent-failure-hunter #2 への対応)。"""
        import logging
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft(player_id=11)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(delay=5.0)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
        ,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers",
        ):
            scheduler.shutdown(timeout=0.1)
        # WARN ログに未完了件数と episode_id が出る
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        msg_blob = " ".join(r.message for r in warns)
        assert "not completed" in msg_blob, f"未完了 WARN が出ていない: {warns}"
        assert draft.episode_id in msg_blob, (
            f"未完了の episode_id が WARN ログに含まれていない: {msg_blob}"
        )

    def test_thread_safety_store_concurrent_read_during_worker_put(self) -> None:
        """ワーカーが put する裏で main thread が list_recent しても壊れない。"""
        # 本テストは player_id=99 で動かす (= _provision_scheduler で別 Being を作る)
        being_99, resolver_99, world_id_99 = _provision_scheduler(99)
        store = InMemorySubjectiveEpisodeStore()
        port = _StubPort(delay=0.05)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store, max_workers=2,
            being_attachment_resolver=resolver_99,
            default_world_id=world_id_99,
        )
        drafts = []
        for i in range(10):
            t = datetime(2026, 6, 1, 9, i, tzinfo=timezone.utc)
            act = ActionResultEntry(
                occurred_at=t,
                action_summary=f"act_{i}",
                result_summary="r",
                tool_name="wait",
                success=True,
            )
            enc_i = build_chunk_encoding_input(PlayerId(99), (), (act,))
            d = ChunkEpisodeDraftBuilder().build(enc_i)
            store.put_by_being(being_99, d)
            scheduler.submit(d, persona_text="", encoding_input=enc_i)
            drafts.append(d)
        try:
            # メインからの並列 read (= 同 store の by_being を読む)
            for _ in range(50):
                res = store.list_recent_by_being(being_99, 20)
                assert isinstance(res, list)
        finally:
            scheduler.shutdown(timeout=3.0)
        # 完了後、全 episode が merged (recall_text="R" に変わる)
        for d in drafts:
            ep_after = store.get_by_being(being_99, d.episode_id)
            assert ep_after is not None
            assert ep_after.recall_text == "R"


# ─────────────────────────────────────────────
# 引数バリデーション
# ─────────────────────────────────────────────


class TestSchedulerValidation:
    """コンストラクタ引数の型 / 値検証。"""

    def test_inline_service_raises_type_error(self) -> None:
        """inline service 型違反は TypeError。"""
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler("not_a_service", store)  # type: ignore[arg-type]

    def test_inline_store_raises_type_error(self) -> None:
        """inline store 型違反は TypeError。"""
        port = _StubPort()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler(
                EpisodicChunkSubjectiveFieldsService(port),
                "not_a_store",  # type: ignore[arg-type]
            )

    def test_threadpool_max_workers(self) -> None:
        """threadpoolmaxworkers は正の整数。"""
        port = _StubPort()
        svc = EpisodicChunkSubjectiveFieldsService(port)
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(ValueError):
            ThreadPoolEpisodicSubjectiveScheduler(svc, store, max_workers=0)
        with pytest.raises(ValueError):
            ThreadPoolEpisodicSubjectiveScheduler(svc, store, max_workers=-1)

    def test_threadpool_max_queue_size(self) -> None:
        """threadpoolmaxqueuesize は正の整数。"""
        port = _StubPort()
        svc = EpisodicChunkSubjectiveFieldsService(port)
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(ValueError):
            ThreadPoolEpisodicSubjectiveScheduler(svc, store, max_queue_size=0)


# ─────────────────────────────────────────────
# U2 (証拠台帳統一設計): 非同期経路での BeliefEvidence 転記
# ─────────────────────────────────────────────


class TestInlineSchedulerBeliefEvidenceTranscription:
    """InlineEpisodicSubjectiveScheduler が完了点で transcriber を呼ぶ挙動。"""

    def test_prediction_error_adds_one_evidence_record(self) -> None:
        """prediction error ありなら evidence が 1件積まれる。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            BeliefEvidenceTranscriber,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "待っても何も起きなかった",
            }
        )
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            belief_evidence_transcriber=transcriber,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].text == "待っても何も起きなかった"

    def test_prediction_error_evidence(self) -> None:
        """predictionerror なしなら evidence は積まれない。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            BeliefEvidenceTranscriber,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            belief_evidence_transcriber=transcriber,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        assert buffer_store.list_all_by_being(being_id) == []

    def test_transcriber_uninjected_flag_off(self) -> None:
        """belief_evidence_transcriber=None (既定) は既存動作と完全互換。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "外れた",
            }
        )
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        # 例外を投げず従来通り完了することだけを確認する。
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.prediction_error == "外れた"

    def test_belief_evidence_transcriber_raises_type_error_2(self) -> None:
        """belief evidence transcriber 型違反は TypeError。"""
        port = _StubPort()
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler(
                EpisodicChunkSubjectiveFieldsService(port),
                store,
                belief_evidence_transcriber="not_a_transcriber",  # type: ignore[arg-type]
            )


class TestInlineSchedulerBeliefAttribution:
    """U4 (予測誤差統一設計 部品3): 非同期経路 (Inline 実装) の attribution + CONFIRMATION。"""

    def test_belief_attribution_enabled_prediction_error_evidence_context_belief_ids_2(
        self,
    ) -> None:
        """belief attribution enabled で prediction error evidence に in context belief ids が添付される。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            BeliefEvidenceTranscriber,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft_with_attribution(
            in_context_belief_ids=("sem-1",), expected_result="何か見つかるはず"
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "何も見つからなかった",
            }
        )
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            belief_evidence_transcriber=transcriber,
            belief_attribution_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].in_context_belief_ids == ("sem-1",)

    def test_belief_attribution_enabled_prediction_error_none_context_belief_expected_result_confirmation(
        self,
    ) -> None:
        """belief attribution enabled で prediction error None かつ in context belief あり expected result ありなら CONFIRMATION。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            BeliefEvidenceTranscriber,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft_with_attribution(
            in_context_belief_ids=("sem-1",), expected_result="何か見つかるはず"
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            belief_evidence_transcriber=transcriber,
            belief_attribution_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind.value == "confirmation"

    def test_belief_attribution_enabled_false_default_context_belief_ids_2(
        self,
    ) -> None:
        """belief attribution enabled False 既定なら in context belief ids を添付しない。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            BeliefEvidenceTranscriber,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft_with_attribution(
            in_context_belief_ids=("sem-1",), expected_result="何か見つかるはず"
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "何も見つからなかった",
            }
        )
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            belief_evidence_transcriber=transcriber,
            belief_attribution_enabled=False,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].in_context_belief_ids == ()


class TestThreadPoolSchedulerBeliefEvidenceTranscription:
    """ThreadPoolEpisodicSubjectiveScheduler (ワーカー thread 経路) も同じ完了点で
    transcriber を呼ぶことを保証する。"""

    def test_prediction_error_adds_one_evidence_record(self) -> None:
        """prediction error ありなら evidence が 1件積まれる。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            BeliefEvidenceTranscriber,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "見つからなかった",
            }
        )
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            belief_evidence_transcriber=transcriber,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        scheduler.shutdown(timeout=5.0)

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].text == "見つからなかった"

    def test_belief_evidence_transcriber_raises_type_error(self) -> None:
        """belief evidence transcriber 型違反は TypeError。"""
        port = _StubPort()
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            ThreadPoolEpisodicSubjectiveScheduler(
                EpisodicChunkSubjectiveFieldsService(port),
                store,
                belief_evidence_transcriber="not_a_transcriber",  # type: ignore[arg-type]
            )


class TestThreadPoolSchedulerBeliefAttribution:
    """U4 (予測誤差統一設計 部品3): 非同期経路 (ThreadPool 実装) の attribution。"""

    def test_belief_attribution_enabled_prediction_error_evidence_context_belief_ids(
        self,
    ) -> None:
        """belief attribution enabled で prediction error evidence に in context belief ids が添付される。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            BeliefEvidenceTranscriber,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft_with_attribution(
            in_context_belief_ids=("sem-1",), expected_result="何か見つかるはず"
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "見つからなかった",
            }
        )
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            belief_evidence_transcriber=transcriber,
            belief_attribution_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        scheduler.shutdown(timeout=5.0)

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].in_context_belief_ids == ("sem-1",)

    def test_belief_attribution_enabled_false_default_context_belief_ids(
        self,
    ) -> None:
        """belief attribution enabled False 既定なら in context belief ids を添付しない。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            BeliefEvidenceTranscriber,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft_with_attribution(
            in_context_belief_ids=("sem-1",), expected_result="何か見つかるはず"
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "見つからなかった",
            }
        )
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            belief_evidence_transcriber=transcriber,
            belief_attribution_enabled=False,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        scheduler.shutdown(timeout=5.0)

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].in_context_belief_ids == ()


class TestInlineSchedulerRecallPredictionOutcomeStamping:
    """U9a (誤差駆動再解釈): InlineEpisodicSubjectiveScheduler の完了点での刻み。"""

    def test_flag_prediction_error_recall_observation_2(
        self,
    ) -> None:
        """flag ON で prediction error ありなら recall observation に誤差が刻まれる。"""
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
        )

        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-1"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_observation(recall_buffer, being_id, prediction_context_id="pc-1")
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "待っても何も起きなかった",
            }
        )
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        obs = recall_buffer.list_pending_by_being(being_id)[0]
        assert obs.prediction_outcome_error == "待っても何も起きなかった"

    def test_flag_off_default_2(self) -> None:
        """error_driven_reinterpretation_enabled=False (既定) は導入前と一致。"""
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
        )

        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-1"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_observation(recall_buffer, being_id, prediction_context_id="pc-1")
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "待っても何も起きなかった",
            }
        )
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=False,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        obs = recall_buffer.list_pending_by_being(being_id)[0]
        assert obs.prediction_outcome_error is None

    def test_default_unwired_recall_buffer_store_completes_without_exception(self) -> None:
        """recall_buffer_store=None (既定) は既存動作と完全互換。"""
        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-1"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "外れた",
            }
        )
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            error_driven_reinterpretation_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.prediction_error == "外れた"

    def test_recall_buffer_store_raises_type_error_2(self) -> None:
        """recall buffer store 型違反は TypeError。"""
        port = _StubPort()
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler(
                EpisodicChunkSubjectiveFieldsService(port),
                store,
                recall_buffer_store="not_a_store",  # type: ignore[arg-type]
            )


class TestThreadPoolSchedulerRecallPredictionOutcomeStamping:
    """U9a (誤差駆動再解釈): ThreadPoolEpisodicSubjectiveScheduler の完了点での刻み。"""

    def test_flag_prediction_error_recall_observation(
        self,
    ) -> None:
        """flag ON で prediction error ありなら recall observation に誤差が刻まれる。"""
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
        )

        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-async"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_observation(
            recall_buffer, being_id, prediction_context_id="pc-async"
        )
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "外れた",
            }
        )
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        scheduler.shutdown(timeout=5.0)

        obs = recall_buffer.list_pending_by_being(being_id)[0]
        assert obs.prediction_outcome_error == "外れた"

    def test_flag_off_default(self) -> None:
        """flag OFF 既定なら誤差は刻まれない。"""
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
        )

        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-async"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_observation(
            recall_buffer, being_id, prediction_context_id="pc-async"
        )
        port = _StubPort(
            returns={
                "interpreted": "I",
                "recall_text": "R",
                "prediction_error": "外れた",
            }
        )
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=False,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        scheduler.shutdown(timeout=5.0)

        obs = recall_buffer.list_pending_by_being(being_id)[0]
        assert obs.prediction_outcome_error is None

    def test_recall_buffer_store_raises_type_error(self) -> None:
        """recall buffer store 型違反は TypeError。"""
        port = _StubPort()
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            ThreadPoolEpisodicSubjectiveScheduler(
                EpisodicChunkSubjectiveFieldsService(port),
                store,
                recall_buffer_store="not_a_store",  # type: ignore[arg-type]
            )


class TestInlineSchedulerRecallHitBoost:
    """U9b (想起の信用割り当て・的中側): InlineEpisodicSubjectiveScheduler の

    完了点での的中側 sidecar への還流。"""

    def test_flag_expected_result_count_incremented_2(
        self,
    ) -> None:
        """flag ON で的中かつexpected resultありなら的中回数が加算される。"""
        from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
            InMemoryEpisodicRecallSuccessStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
        )

        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-1", expected_result="見つかるはず"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_observation(recall_buffer, being_id, prediction_context_id="pc-1")
        recall_success = InMemoryEpisodicRecallSuccessStore()
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=True,
            recall_success_store=recall_success,
            recall_hit_boost_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        assert recall_success.get_hit_count_by_being(being_id, "ep-source") == 1

    def test_flag_off_default_not_incremented_2(self) -> None:
        """flag OFF 既定なら加算されない。"""
        from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
            InMemoryEpisodicRecallSuccessStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
        )

        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-1", expected_result="見つかるはず"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_observation(recall_buffer, being_id, prediction_context_id="pc-1")
        recall_success = InMemoryEpisodicRecallSuccessStore()
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=True,
            recall_success_store=recall_success,
            recall_hit_boost_enabled=False,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        assert recall_success.get_hit_count_by_being(being_id, "ep-source") == 0

    def test_default_unwired_recall_success_store_completes_without_exception(self) -> None:
        """recall success store 未配線 既定なら例外を投げず完了する。"""
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
        )

        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-1", expected_result="見つかるはず"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_observation(recall_buffer, being_id, prediction_context_id="pc-1")
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=True,
            recall_hit_boost_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None

    def test_recall_success_store_raises_type_error_2(self) -> None:
        """recall success store 型違反は TypeError。"""
        port = _StubPort()
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler(
                EpisodicChunkSubjectiveFieldsService(port),
                store,
                recall_success_store="not_a_store",  # type: ignore[arg-type]
            )


class TestThreadPoolSchedulerRecallHitBoost:
    """U9b (想起の信用割り当て・的中側): ThreadPoolEpisodicSubjectiveScheduler の

    完了点での的中側 sidecar への還流。"""

    def test_flag_expected_result_count_incremented(
        self,
    ) -> None:
        """flag ON で的中かつexpected resultありなら的中回数が加算される。"""
        from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
            InMemoryEpisodicRecallSuccessStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
        )

        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-async", expected_result="見つかるはず"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_observation(
            recall_buffer, being_id, prediction_context_id="pc-async"
        )
        recall_success = InMemoryEpisodicRecallSuccessStore()
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=True,
            recall_success_store=recall_success,
            recall_hit_boost_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        scheduler.shutdown(timeout=5.0)

        assert recall_success.get_hit_count_by_being(being_id, "ep-source") == 1

    def test_flag_off_default_not_incremented(self) -> None:
        """flag OFF 既定なら加算されない。"""
        from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
            InMemoryEpisodicRecallSuccessStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
        )

        enc, draft, being_id, resolver, world_id = (
            _build_encoding_and_draft_with_prediction_context_id(
                prediction_context_id="pc-async", expected_result="見つかるはず"
            )
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        _seed_recall_observation(
            recall_buffer, being_id, prediction_context_id="pc-async"
        )
        recall_success = InMemoryEpisodicRecallSuccessStore()
        port = _StubPort(returns={"interpreted": "I", "recall_text": "R"})
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            recall_buffer_store=recall_buffer,
            error_driven_reinterpretation_enabled=True,
            recall_success_store=recall_success,
            recall_hit_boost_enabled=False,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        scheduler.shutdown(timeout=5.0)

        assert recall_success.get_hit_count_by_being(being_id, "ep-source") == 0

    def test_recall_success_store_raises_type_error(self) -> None:
        """recall success store 型違反は TypeError。"""
        port = _StubPort()
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            ThreadPoolEpisodicSubjectiveScheduler(
                EpisodicChunkSubjectiveFieldsService(port),
                store,
                recall_success_store="not_a_store",  # type: ignore[arg-type]
            )


# ─────────────────────────────────────────────
# H-2 (自己言及ループ): submit(actor_name=...) が heard_claims の自己言及
# フィルタまで伝わること (非同期経路)。単体の正規化ロジック自体は
# test_episodic_chunk_subjective_fields_hearsay.py で検証済みなので、ここでは
# scheduler.submit → _service.merge_llm_subjective_fields への配線のみを見る。
# ─────────────────────────────────────────────

_HEARD_CLAIMS_RETURN = {
    "interpreted": "I",
    "recall_text": "R",
    "heard_claims": [
        {"speaker": "カイト", "claim": "自分の発言"},
        {"speaker": "リオ", "claim": "北の泉は安全だ"},
    ],
}


class TestInlineSchedulerActorNamePropagation:
    def test_actor_name_self_speaker_claim_rejected_2(self) -> None:
        """actor name を渡すと本人speakerのclaimが弾かれる。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns=_HEARD_CLAIMS_RETURN)
        service = EpisodicChunkSubjectiveFieldsService(port, hearsay_enabled=True)
        scheduler = InlineEpisodicSubjectiveScheduler(
            service, store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(
            draft, persona_text="", encoding_input=enc, actor_name="カイト"
        )
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert [c.speaker for c in ep_after.heard_claims] == ["リオ"]

    def test_actor_name_line(self) -> None:
        """未指定 (デフォルト None) では従来通り全ての speaker を通す

        (後方互換: actor_name を渡さない既存呼び出し元の挙動を変えない)。
        """
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns=_HEARD_CLAIMS_RETURN)
        service = EpisodicChunkSubjectiveFieldsService(port, hearsay_enabled=True)
        scheduler = InlineEpisodicSubjectiveScheduler(
            service, store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert [c.speaker for c in ep_after.heard_claims] == ["カイト", "リオ"]


class TestThreadPoolSchedulerActorNamePropagation:
    def test_actor_name_self_speaker_claim_rejected(self) -> None:
        """actor name を渡すと本人speakerのclaimが弾かれる。"""
        enc, draft, being_id, resolver, world_id = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns=_HEARD_CLAIMS_RETURN)
        service = EpisodicChunkSubjectiveFieldsService(port, hearsay_enabled=True)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            service, store,
            max_workers=1,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
        )
        try:
            scheduler.submit(
                draft, persona_text="", encoding_input=enc, actor_name="カイト"
            )
            scheduler.shutdown()
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert [c.speaker for c in ep_after.heard_claims] == ["リオ"]


# ─────────────────────────────────────────────
# LOW-4: 約束の記録 (record_pending_prediction_if_applicable) の失敗が
# 「LLM 補完が失敗」に誤報告されず、同 chunk の清算 (resolve) も
# 巻き添えで skip されないこと。
# ─────────────────────────────────────────────


class _RaisingOnAddPendingPredictionStore(InMemoryPendingPredictionStore):
    """記録 (add_by_being) だけを失敗させる fake store。

    list_all_by_being / replace_all_by_being は正常に動く基底実装のままにし、
    清算 (resolve_pending_predictions_if_applicable) が記録の失敗と無関係に
    動くことを検証できるようにする。
    """

    def add_by_being(self, being_id, pending):  # type: ignore[override]
        raise RuntimeError("boom-pending-add")


def _build_pending_prediction_sidecar_fixture(*, player_id: int = 7):
    """約束の記録 (pending_prediction) と清算 (pending_resolution) の両方を

    同じ chunk で LLM に返させるための一式を組み立てる。

    - LLM 応答に ``pending_prediction`` (新しい約束) と ``pending_resolutions``
      (既存約束 "p1" への fulfilled 判定) を両方含める
    - encoding_input.active_pending_predictions に既存約束 "p1" を乗せておく
      (清算対象として正規化されるために必要)
    """
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(
        occurred_at=t,
        action_summary="カイトと話した",
        result_summary="約束を交わした",
        tool_name="interact",
        success=True,
    )
    existing_pending = PendingPrediction(
        pending_id="p1",
        text="約束-p1",
        # PR-C 共在ゲート: player cue にすると fulfilled 受理に episode.who
        # への実在が要る。この fixture の draft には observations が無く
        # who は空になるため、ゲート対象外の spot cue にしてこのテストの
        # 本来の関心 (add 失敗が resolve を巻き添えにしないこと) を保つ。
        resolution_cues=("spot:1",),
        tick_from=1,
        tick_to=50,
        origin_episode_id="ep-origin",
        created_tick=1,
    )
    enc = build_chunk_encoding_input(
        PlayerId(player_id),
        (),
        (act,),
        active_pending_predictions=(existing_pending,),
    )
    draft = ChunkEpisodeDraftBuilder().build(enc)
    being_id, resolver, world_id = _provision_scheduler(player_id)
    port = _StubPort(
        returns={
            "interpreted": "I",
            "recall_text": "R",
            "pending_prediction": {
                "text": "夕方に木の下でカイトと交換する",
                "resolution_cues": ["player:カイト"],
                "tick_offset_from": 2,
                "tick_offset_to": 6,
            },
            "pending_resolutions": [{"pending_id": "p1", "verdict": "fulfilled"}],
        }
    )
    service = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
    return enc, draft, being_id, resolver, world_id, service, existing_pending


class TestInlineSchedulerPendingPredictionSidecarIsolation:
    """約束の記録経路が失敗しても、補完自体の成否や清算の実行が正しく報告される。"""

    def test_failure_failed_filled_trace_episode_merged_saved_2(
        self,
    ) -> None:
        """約束の記録が失敗しても FAILED ではなく FILLED trace になり episode はmergedで保存される。"""
        enc, draft, being_id, resolver, world_id, service, existing_pending = (
            _build_pending_prediction_sidecar_fixture()
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        pending_store = _RaisingOnAddPendingPredictionStore()
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(
            service,
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 10,
            pending_prediction_store=pending_store,
            pending_prediction_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        filled = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FILLED]
        assert failed == [], "約束の記録の失敗が補完失敗と誤報告されてはいけない"
        assert len(filled) == 1
        # merge 自体は成功しているので episode は draft ではなく merged で保存される。
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.interpreted == "I"

    def test_failure_same_chunk_line_2(self) -> None:
        """記録 (add) の失敗が清算 (resolve) を巻き添えにしないことを保証する。"""
        enc, draft, being_id, resolver, world_id, service, existing_pending = (
            _build_pending_prediction_sidecar_fixture()
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        pending_store = _RaisingOnAddPendingPredictionStore()
        # add_by_being 以外の primitive で既存約束を仕込む (add は必ず失敗する)。
        pending_store.replace_all_by_being(being_id, [existing_pending])
        scheduler = InlineEpisodicSubjectiveScheduler(
            service,
            store,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            current_tick_provider=lambda: 10,
            pending_prediction_store=pending_store,
            pending_prediction_enabled=True,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)

        # p1 は fulfilled 判定を受けて清算され、store から除かれているはず。
        remaining = pending_store.list_all_by_being(being_id)
        assert remaining == [], (
            "約束の記録が失敗しても、同じ chunk の清算 (resolve) は独立して "
            "実行されるべき"
        )


class TestThreadPoolSchedulerPendingPredictionSidecarIsolation:
    """ThreadPool 版の ``_worker`` にも Inline と同じ分離が適用されていること。"""

    def test_failure_failed_filled_trace_episode_merged_saved(
        self,
    ) -> None:
        """約束の記録が失敗しても FAILED ではなく FILLED trace になり episode はmergedで保存される。"""
        enc, draft, being_id, resolver, world_id, service, existing_pending = (
            _build_pending_prediction_sidecar_fixture()
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        pending_store = _RaisingOnAddPendingPredictionStore()
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            service,
            store,
            max_workers=1,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 10,
            pending_prediction_store=pending_store,
            pending_prediction_enabled=True,
        )
        try:
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            scheduler.shutdown(timeout=5.0)
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise

        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        filled = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FILLED]
        assert failed == [], "約束の記録の失敗が補完失敗と誤報告されてはいけない"
        assert len(filled) == 1
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.interpreted == "I"

    def test_failure_same_chunk_line(self) -> None:
        """約束の記録が失敗しても同じchunkの清算は実行される。"""
        enc, draft, being_id, resolver, world_id, service, existing_pending = (
            _build_pending_prediction_sidecar_fixture()
        )
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        pending_store = _RaisingOnAddPendingPredictionStore()
        pending_store.replace_all_by_being(being_id, [existing_pending])
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            service,
            store,
            max_workers=1,
            being_attachment_resolver=resolver,
            default_world_id=world_id,
            current_tick_provider=lambda: 10,
            pending_prediction_store=pending_store,
            pending_prediction_enabled=True,
        )
        try:
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            scheduler.shutdown(timeout=5.0)
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise

        remaining = pending_store.list_all_by_being(being_id)
        assert remaining == [], (
            "約束の記録が失敗しても、同じ chunk の清算 (resolve) は独立して "
            "実行されるべき"
        )
