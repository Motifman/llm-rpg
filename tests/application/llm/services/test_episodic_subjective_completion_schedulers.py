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
from ai_rpg_world.application.llm.contracts.episodic_chunk_subjective_llm_port import (
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
    """最小限の ChunkEncodingInput + draft Episode を作る。"""
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(
        occurred_at=t,
        action_summary="待機した",
        result_summary="時間が進んだ",
        tool_name="spot_graph_wait",
        success=True,
    )
    enc = build_chunk_encoding_input(PlayerId(player_id), (), (act,))
    draft = ChunkEpisodeDraftBuilder().build(enc)
    return enc, draft


# ─────────────────────────────────────────────
# InlineEpisodicSubjectiveScheduler
# ─────────────────────────────────────────────


class TestInlineScheduler:
    """同期 scheduler が同じ thread 内で merge → store 上書きを完結させる。"""

    def test_submit_で_store_の_episode_が_LLM_文に上書きされる(self) -> None:
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)  # chunk_coordinator が事前に draft を入れた状態を模す
        port = _StubPort(returns={"interpreted": "STUB_I", "recall_text": "STUB_R"})
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
        )
        scheduler.submit(draft, persona_text="ペルソナ", encoding_input=enc)
        ep_after = store.get(draft.player_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.interpreted == "STUB_I"
        assert ep_after.recall_text == "STUB_R"
        assert port.call_count == 1

    def test_LLM_失敗時は_draft_のまま_FAILED_trace_を出す(self) -> None:
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
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
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        assert len(failed) == 1
        assert failed[0].player_id == int(draft.player_id)
        assert failed[0].tick == 42
        assert failed[0].payload["episode_id"] == draft.episode_id
        # store の episode は draft のまま (上書き無し)
        ep_after = store.get(draft.player_id, draft.episode_id)
        assert ep_after == draft

    def test_FILLED_trace_の_recall_text_snippet_は_120_文字まで(self) -> None:
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
        long_recall = "あ" * 500
        port = _StubPort(returns={"interpreted": "X", "recall_text": long_recall})
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            trace_recorder_provider=lambda: recorder,
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        filled = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FILLED]
        assert len(filled) == 1
        assert len(filled[0].payload["recall_text_snippet"]) <= 120

    def test_shutdown_は_noop(self) -> None:
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        port = _StubPort()
        scheduler = InlineEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
        )
        scheduler.shutdown()  # 例外なく終わる
        scheduler.shutdown(timeout=1.0)  # 何度呼んでも安全


# ─────────────────────────────────────────────
# ThreadPoolEpisodicSubjectiveScheduler
# ─────────────────────────────────────────────


class TestThreadPoolScheduler:
    """非同期 scheduler が裏で merge → store 上書きを完了する。"""

    def test_submit_後_shutdown_で_store_が_LLM_文に上書きされる(self) -> None:
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
        port = _StubPort(returns={"interpreted": "ASYNC_I", "recall_text": "ASYNC_R"})
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port),
            store,
            max_workers=1,
        )
        try:
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            scheduler.shutdown()  # drain
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        ep_after = store.get(draft.player_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.recall_text == "ASYNC_R"
        assert ep_after.interpreted == "ASYNC_I"

    def test_submit_は_非ブロッキング(self) -> None:
        """重い LLM (1 秒 sleep) を投げても submit は瞬時に返る。"""
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
        port = _StubPort(delay=1.0)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
        )
        try:
            t0 = time.monotonic()
            scheduler.submit(draft, persona_text="", encoding_input=enc)
            elapsed = time.monotonic() - t0
            assert elapsed < 0.2, f"submit がブロックした: {elapsed:.3f}s"
        finally:
            scheduler.shutdown(timeout=2.0)

    def test_LLM_失敗時_は_draft_のまま_FAILED_trace_が出る(self) -> None:
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
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
        )
        scheduler.submit(draft, persona_text="", encoding_input=enc)
        scheduler.shutdown()
        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        assert len(failed) == 1
        # draft が store に残っている (上書き無し)
        assert store.get(draft.player_id, draft.episode_id) == draft

    def test_同一_episode_id_の_重複_submit_は_dedupe_される(self) -> None:
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
        # delay を入れて 2 回目の submit が 1 回目と同時 in-flight になるよう仕組む
        port = _StubPort(delay=0.3)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
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
        enc1, draft1 = _build_encoding_and_draft(player_id=1)
        enc2, draft2 = _build_encoding_and_draft(player_id=2)
        enc3, draft3 = _build_encoding_and_draft(player_id=3)
        store = InMemorySubjectiveEpisodeStore()
        for d in (draft1, draft2, draft3):
            store.put(d)
        # 全 worker が詰まるように長めの delay
        port = _StubPort(delay=0.5)
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store,
            max_workers=1,
            max_queue_size=2,
            trace_recorder_provider=lambda: recorder,
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
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
        port = _StubPort()
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store,
            trace_recorder_provider=lambda: recorder,
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
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
        # 5 秒寝るので 0.1 秒 timeout では完了しない
        port = _StubPort(delay=5.0)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
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
        enc, draft = _build_encoding_and_draft(player_id=11)
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
        port = _StubPort(delay=5.0)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store
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
        enc, draft = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put(draft)
        port = _StubPort(delay=0.05)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            EpisodicChunkSubjectiveFieldsService(port), store, max_workers=2
        )
        # 同じ player に対して 10 件 chunk を投入し、メインから list_recent を回す
        drafts = []
        for i in range(10):
            t = datetime(2026, 6, 1, 9, i, tzinfo=timezone.utc)
            act = ActionResultEntry(
                occurred_at=t,
                action_summary=f"act_{i}",
                result_summary="r",
                tool_name="spot_graph_wait",
                success=True,
            )
            enc_i = build_chunk_encoding_input(PlayerId(99), (), (act,))
            d = ChunkEpisodeDraftBuilder().build(enc_i)
            store.put(d)
            scheduler.submit(d, persona_text="", encoding_input=enc_i)
            drafts.append(d)
        try:
            # メインからの並列 read
            for _ in range(50):
                res = store.list_recent(99, 20)
                # 壊れた dict / 例外なく取得できれば OK
                assert isinstance(res, list)
        finally:
            scheduler.shutdown(timeout=3.0)
        # 完了後、全 episode が merged (recall_text != draft.recall_text)
        for d in drafts:
            ep_after = store.get(99, d.episode_id)
            assert ep_after is not None
            # stub は recall_text="R" を返す。draft の recall_text と一致しないことを確認
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
