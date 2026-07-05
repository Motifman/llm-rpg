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
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.trace import (
    ITraceRecorder,
    NullTraceRecorder,
    TraceEventKind,
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

    def test_submit_で_store_の_episode_が_LLM_文に上書きされる(self) -> None:
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

    def test_LLM_失敗時は_draft_のまま_FAILED_trace_を出す(self) -> None:
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

    def test_FILLED_trace_の_recall_text_snippet_は_120_文字まで(self) -> None:
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

    def test_U1_prediction_error_確定時に_PREDICTION_OUTCOME_が_id_付きで出る(
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

    def test_U1_prediction_error_が_None_でも_in_context_id_があれば_PREDICTION_OUTCOME_は出る(
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

    def test_U1_id_機構_OFF_相当_id無しなら_PREDICTION_OUTCOME_は出ない(self) -> None:
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

    def test_shutdown_は_noop(self) -> None:
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

    def test_submit_後_shutdown_で_store_が_LLM_文に上書きされる(self) -> None:
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

    def test_U1_in_context_id_があれば_PREDICTION_OUTCOME_が_id_付きで出る(self) -> None:
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

    def test_U1_id_機構_OFF_相当_id無しなら_PREDICTION_OUTCOME_は出ない(self) -> None:
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

    def test_submit_は_非ブロッキング(self) -> None:
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

    def test_LLM_失敗時_は_draft_のまま_FAILED_trace_が出る(self) -> None:
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

    def test_同一_episode_id_の_重複_submit_は_dedupe_される(self) -> None:
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

    def test_max_queue_size_超過で_DROPPED_trace_が出る(self) -> None:
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

    def test_shutdown_後の_submit_は_DROPPED_trace_付きで_drop_される(self) -> None:
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

    def test_shutdown_timeout_で_未完了は_諦める(self) -> None:
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

    def test_shutdown_timeout_未完了は_WARN_log_で_観測可能(
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

    def test_inline_service_型違反は_TypeError(self) -> None:
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler("not_a_service", store)  # type: ignore[arg-type]

    def test_inline_store_型違反は_TypeError(self) -> None:
        port = _StubPort()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler(
                EpisodicChunkSubjectiveFieldsService(port),
                "not_a_store",  # type: ignore[arg-type]
            )

    def test_threadpool_max_workers_は_正の整数(self) -> None:
        port = _StubPort()
        svc = EpisodicChunkSubjectiveFieldsService(port)
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(ValueError):
            ThreadPoolEpisodicSubjectiveScheduler(svc, store, max_workers=0)
        with pytest.raises(ValueError):
            ThreadPoolEpisodicSubjectiveScheduler(svc, store, max_workers=-1)

    def test_threadpool_max_queue_size_は_正の整数(self) -> None:
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

    def test_prediction_error_ありなら_evidence_が_1件積まれる(self) -> None:
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

    def test_prediction_error_なしなら_evidence_は_積まれない(self) -> None:
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

    def test_transcriber_未注入なら_flag_OFF_相当で何も積まない(self) -> None:
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

    def test_belief_evidence_transcriber_型違反は_TypeError(self) -> None:
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

    def test_belief_attribution_enabled_で_prediction_error_evidence_に_in_context_belief_ids_が添付される(
        self,
    ) -> None:
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

    def test_belief_attribution_enabled_で_prediction_error_None_かつ_in_context_belief_あり_expected_result_ありなら_CONFIRMATION(
        self,
    ) -> None:
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

    def test_belief_attribution_enabled_False_既定なら_in_context_belief_ids_を添付しない(
        self,
    ) -> None:
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

    def test_prediction_error_ありなら_evidence_が_1件積まれる(self) -> None:
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

    def test_belief_evidence_transcriber_型違反は_TypeError(self) -> None:
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

    def test_belief_attribution_enabled_で_prediction_error_evidence_に_in_context_belief_ids_が添付される(
        self,
    ) -> None:
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

    def test_belief_attribution_enabled_False_既定なら_in_context_belief_ids_を添付しない(
        self,
    ) -> None:
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

    def test_flag_ON_で_prediction_error_ありなら_recall_observation_に誤差が刻まれる(
        self,
    ) -> None:
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

    def test_flag_OFF_既定なら誤差は刻まれない(self) -> None:
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

    def test_recall_buffer_store_未配線_既定なら例外を投げず完了する(self) -> None:
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

    def test_recall_buffer_store_型違反は_TypeError(self) -> None:
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

    def test_flag_ON_で_prediction_error_ありなら_recall_observation_に誤差が刻まれる(
        self,
    ) -> None:
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

    def test_flag_OFF_既定なら誤差は刻まれない(self) -> None:
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

    def test_recall_buffer_store_型違反は_TypeError(self) -> None:
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

    def test_flag_ON_で的中かつexpected_resultありなら的中回数が加算される(
        self,
    ) -> None:
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

    def test_flag_OFF_既定なら加算されない(self) -> None:
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

    def test_recall_success_store_未配線_既定なら例外を投げず完了する(self) -> None:
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

    def test_recall_success_store_型違反は_TypeError(self) -> None:
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

    def test_flag_ON_で的中かつexpected_resultありなら的中回数が加算される(
        self,
    ) -> None:
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

    def test_flag_OFF_既定なら加算されない(self) -> None:
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

    def test_recall_success_store_型違反は_TypeError(self) -> None:
        port = _StubPort()
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            ThreadPoolEpisodicSubjectiveScheduler(
                EpisodicChunkSubjectiveFieldsService(port),
                store,
                recall_success_store="not_a_store",  # type: ignore[arg-type]
            )
