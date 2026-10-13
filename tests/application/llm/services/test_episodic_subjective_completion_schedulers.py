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

import time
from datetime import datetime, timezone
from typing import Any

import pytest
from tests.memory_turn_helpers import ZERO_TURN

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    build_chunk_encoding_input,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import ChunkEpisodeDraftBuilder
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import EpisodicChunkSubjectiveFieldsService
from ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers import (
    InlineEpisodicSubjectiveScheduler,
    ThreadPoolEpisodicSubjectiveScheduler,
)
from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import InMemoryPendingPredictionStore
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import PendingPrediction
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _capture(recorder: NullTraceRecorder) -> list:
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev
    recorder.record = wrapper
    return captured

class _StubPort(IEpisodicChunkSubjectiveCompletionPort):

    def __init__(self, *, returns: dict | None=None, raises: BaseException | None=None, delay: float=0.0):
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
        return self._returns or {'interpreted': 'I', 'recall_text': 'R'}

def _build_encoding_and_draft(*, player_id: int=7) -> tuple:
    """最小限の ChunkEncodingInput + draft Episode + Being 一式を作る。

    Phase 3 Step 3e-3: scheduler は being_id 経路必須となったため、helper で
    Being 解決一式 (being_id / resolver / world_id) も同時に返す。
    返り値: ``(enc, draft, being_id, resolver, world_id)``。
    """
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(occurred_at=t, action_summary='待機した', result_summary='時間が進んだ', tool_name='wait', success=True)
    enc = build_chunk_encoding_input(PlayerId(player_id), (), (act,))
    (being_id, resolver, world_id) = _provision_scheduler(player_id)
    draft = ChunkEpisodeDraftBuilder().build(enc, being_id=being_id)
    return (enc, draft, being_id, resolver, world_id)

def _provision_scheduler(player_id: int):
    """Phase 3 Step 3e-3: 各テストで scheduler に Resolver を inject するための
    Being+Resolver+WorldId 一式を組み立てる helper。

    返り値: ``(being_id, resolver, world_id)``。
    """
    from ai_rpg_world.application.being.being_attachment_resolver import BeingAttachmentResolver
    from ai_rpg_world.application.being.being_provisioning_service import BeingProvisioningService
    from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
    from ai_rpg_world.infrastructure.repository.in_memory_being_repository import InMemoryBeingRepository
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    being_id = BeingProvisioningService(repo).ensure_attached(PlayerId(player_id))
    return (being_id, resolver, DEFAULT_SINGLE_WORLD_ID)

class TestInlineScheduler:
    """同期 scheduler が同じ thread 内で merge → store 上書きを完結させる。"""

    def test_submit_store_episode_llm_overwritten(self) -> None:
        """submit で store の episode が LLM 文に上書きされる。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns={'interpreted': 'STUB_I', 'recall_text': 'STUB_R'})
        scheduler = InlineEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store)
        scheduler.submit(draft, persona_text='ペルソナ', encoding_input=enc)
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.interpreted == 'STUB_I'
        assert ep_after.recall_text == 'STUB_R'
        assert port.call_count == 1

    def test_llm_failure_draft_failed_trace(self) -> None:
        """LLM 失敗時は draft のまま FAILED trace を出す。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)

        class _BoomService(EpisodicChunkSubjectiveFieldsService):

            def merge_llm_subjective_fields(self, *a, **kw):
                raise RuntimeError('scheduler-level boom')
        port = _StubPort()
        bad_svc = _BoomService(port)
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(bad_svc, store, trace_recorder_provider=lambda : recorder, current_tick_provider=lambda : 42)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        assert len(failed) == 1
        assert failed[0].player_id == int(draft.player_id)
        assert failed[0].tick == 42
        assert failed[0].payload['episode_id'] == draft.episode_id
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after == draft

    def test_filled_trace_recall_text_snippet_120(self) -> None:
        """FILLED trace の recall text snippet は 120 文字まで。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        long_recall = 'あ' * 500
        port = _StubPort(returns={'interpreted': 'X', 'recall_text': long_recall})
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, trace_recorder_provider=lambda : recorder)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        filled = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FILLED]
        assert len(filled) == 1
        assert len(filled[0].payload['recall_text_snippet']) <= 120

    def test_shutdown_noop(self) -> None:
        """shutdown は noop。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        port = _StubPort()
        scheduler = InlineEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store)
        scheduler.shutdown()
        scheduler.shutdown(timeout=1.0)

class TestThreadPoolScheduler:
    """非同期 scheduler が裏で merge → store 上書きを完了する。"""

    def test_submit_after_shutdown_store_llm_overwritten(self) -> None:
        """submit 後 shutdown で store が LLM 文に上書きされる。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns={'interpreted': 'ASYNC_I', 'recall_text': 'ASYNC_R'})
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, max_workers=1)
        try:
            scheduler.submit(draft, persona_text='', encoding_input=enc)
            scheduler.shutdown()
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.recall_text == 'ASYNC_R'
        assert ep_after.interpreted == 'ASYNC_I'

    def test_submit_non(self) -> None:
        """重い LLM (1 秒 sleep) を投げても submit は瞬時に返る。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(delay=1.0)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store)
        try:
            t0 = time.monotonic()
            scheduler.submit(draft, persona_text='', encoding_input=enc)
            elapsed = time.monotonic() - t0
            assert elapsed < 0.2, f'submit がブロックした: {elapsed:.3f}s'
        finally:
            scheduler.shutdown(timeout=2.0)

    def test_llm_failure_draft_failed_trace_rendered(self) -> None:
        """LLM 失敗時は draft のまま FAILEDtrace が出る。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)

        class _BoomService(EpisodicChunkSubjectiveFieldsService):

            def merge_llm_subjective_fields(self, *a, **kw):
                raise LlmApiCallException('down', error_code='LLM_API_CALL_FAILED')
        port = _StubPort()
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(_BoomService(port), store, trace_recorder_provider=lambda : recorder)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        scheduler.shutdown()
        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        assert len(failed) == 1
        assert store.get_by_being(being_id, draft.episode_id) == draft

    def test_same_episode_id_duplicate_submit_dedupe(self) -> None:
        """同一 episodeid の重複 submit は dedupe される。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(delay=0.3)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store)
        try:
            scheduler.submit(draft, persona_text='', encoding_input=enc)
            scheduler.submit(draft, persona_text='', encoding_input=enc)
            scheduler.submit(draft, persona_text='', encoding_input=enc)
            scheduler.shutdown()
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        assert port.call_count == 1

    def test_max_queue_size_exceeds_dropped_trace_rendered(self) -> None:
        """max_queue_size=2 に設定して 3 件投げると 1 件は drop される。"""
        (enc1, draft1, being1, resolver, world_id) = _build_encoding_and_draft(player_id=1)
        (enc2, draft2, being2, _, _) = _build_encoding_and_draft(player_id=2)
        (enc3, draft3, being3, _, _) = _build_encoding_and_draft(player_id=3)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being1, draft1)
        store.put_by_being(being2, draft2)
        store.put_by_being(being3, draft3)
        port = _StubPort(delay=0.5)
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, max_workers=1, max_queue_size=2, trace_recorder_provider=lambda : recorder)
        try:
            scheduler.submit(draft1, persona_text='', encoding_input=enc1)
            scheduler.submit(draft2, persona_text='', encoding_input=enc2)
            scheduler.submit(draft3, persona_text='', encoding_input=enc3)
        finally:
            scheduler.shutdown(timeout=3.0)
        dropped = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_DROPPED]
        assert len(dropped) == 1
        assert dropped[0].payload['episode_id'] == draft3.episode_id
        assert dropped[0].payload['max_queue_size'] == 2

    def test_shutdown_after_submit_dropped_trace_drop(self) -> None:
        """無音 drop ではなく観測可能にする (silent-failure-hunter #1 への対応)。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort()
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, trace_recorder_provider=lambda : recorder)
        scheduler.shutdown()
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        assert port.call_count == 0
        dropped = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_DROPPED]
        assert len(dropped) == 1
        assert dropped[0].payload['episode_id'] == draft.episode_id
        assert dropped[0].payload['reason'] == 'shutdown'

    def test_shutdown_timeout(self) -> None:
        """shutdowntimeout で未完了は諦める。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(delay=5.0)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        t0 = time.monotonic()
        scheduler.shutdown(timeout=0.1)
        elapsed = time.monotonic() - t0
        assert elapsed < 1.5, f'shutdown が長すぎる: {elapsed:.2f}s'

    def test_shutdown_timeout_warn_log_observation(self, caplog: pytest.LogCaptureFixture) -> None:
        """timeout 超過ジョブは episode_id 付きで WARN ログに出る
        (silent-failure-hunter #2 への対応)。"""
        import logging
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft(player_id=11)
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(delay=5.0)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        with caplog.at_level(logging.WARNING, logger='ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers'):
            scheduler.shutdown(timeout=0.1)
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        msg_blob = ' '.join(r.message for r in warns)
        assert 'not completed' in msg_blob, f'未完了 WARN が出ていない: {warns}'
        assert draft.episode_id in msg_blob, f'未完了の episode_id が WARN ログに含まれていない: {msg_blob}'

    def test_thread_safety_store_concurrent_read_during_worker_put(self) -> None:
        """ワーカーが put する裏で main thread が list_recent しても壊れない。"""
        (being_99, resolver_99, world_id_99) = _provision_scheduler(99)
        store = InMemorySubjectiveEpisodeStore()
        port = _StubPort(delay=0.05)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, max_workers=2)
        drafts = []
        for i in range(10):
            t = datetime(2026, 6, 1, 9, i, tzinfo=timezone.utc)
            act = ActionResultEntry(occurred_at=t, action_summary=f'act_{i}', result_summary='r', tool_name='wait', success=True)
            enc_i = build_chunk_encoding_input(PlayerId(99), (), (act,))
            d = ChunkEpisodeDraftBuilder().build(enc_i, being_id=being_99)
            store.put_by_being(being_99, d)
            scheduler.submit(d, persona_text='', encoding_input=enc_i)
            drafts.append(d)
        try:
            for _ in range(50):
                res = store.list_recent_by_being(being_99, 20)
                assert isinstance(res, list)
        finally:
            scheduler.shutdown(timeout=3.0)
        for d in drafts:
            ep_after = store.get_by_being(being_99, d.episode_id)
            assert ep_after is not None
            assert ep_after.recall_text == 'R'

class TestSchedulerValidation:
    """コンストラクタ引数の型 / 値検証。"""

    def test_inline_service_raises_type_error(self) -> None:
        """inline service 型違反は TypeError。"""
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler('not_a_service', store)

    def test_inline_store_raises_type_error(self) -> None:
        """inline store 型違反は TypeError。"""
        port = _StubPort()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), 'not_a_store')

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

class TestInlineSchedulerBeliefEvidenceTranscription:
    """InlineEpisodicSubjectiveScheduler が完了点で transcriber を呼ぶ挙動。"""

    def test_prediction_error_of_chunk_adds_no_evidence(self) -> None:
        """chunk の prediction_error は証拠にしない。予測の当否は確定した予期から積む (#1443)。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import BeliefEvidenceTranscriber
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        port = _StubPort(returns={'interpreted': 'I', 'recall_text': 'R', 'prediction_error': '待っても何も起きなかった'})
        scheduler = InlineEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, belief_evidence_transcriber=transcriber)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        assert buffer_store.list_all_by_being(being_id) == []

    def test_prediction_error_evidence(self) -> None:
        """predictionerror なしなら evidence は積まれない。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import BeliefEvidenceTranscriber
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        port = _StubPort(returns={'interpreted': 'I', 'recall_text': 'R'})
        scheduler = InlineEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, belief_evidence_transcriber=transcriber)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        assert buffer_store.list_all_by_being(being_id) == []

    def test_transcriber_uninjected_flag_off(self) -> None:
        """belief_evidence_transcriber=None (既定) でも主観補完は episode に書き戻される。"""
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        port = _StubPort(returns={'interpreted': '待ちくたびれた', 'recall_text': 'R'})
        scheduler = InlineEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.interpreted == '待ちくたびれた'

    def test_belief_evidence_transcriber_raises_type_error_2(self) -> None:
        """belief evidence transcriber 型違反は TypeError。"""
        port = _StubPort()
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            InlineEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, belief_evidence_transcriber='not_a_transcriber')

class TestThreadPoolSchedulerBeliefEvidenceTranscription:
    """ThreadPoolEpisodicSubjectiveScheduler (ワーカー thread 経路) も同じ完了点で
    transcriber を呼ぶことを保証する。"""

    def test_prediction_error_of_chunk_adds_no_evidence(self) -> None:
        """ワーカー経路でも chunk の prediction_error は証拠にしない (#1443)。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import BeliefEvidenceTranscriber
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )
        (enc, draft, being_id, resolver, world_id) = _build_encoding_and_draft()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        port = _StubPort(returns={'interpreted': 'I', 'recall_text': 'R', 'prediction_error': '見つからなかった'})
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, belief_evidence_transcriber=transcriber)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        scheduler.shutdown(timeout=5.0)
        assert buffer_store.list_all_by_being(being_id) == []

    def test_belief_evidence_transcriber_raises_type_error(self) -> None:
        """belief evidence transcriber 型違反は TypeError。"""
        port = _StubPort()
        store = InMemorySubjectiveEpisodeStore()
        with pytest.raises(TypeError):
            ThreadPoolEpisodicSubjectiveScheduler(EpisodicChunkSubjectiveFieldsService(port), store, belief_evidence_transcriber='not_a_transcriber')

class _RaisingOnAddPendingPredictionStore(InMemoryPendingPredictionStore):
    """記録 (add_by_being) だけを失敗させる fake store。

    list_all_by_being / replace_all_by_being は正常に動く基底実装のままにし、
    清算 (resolve_pending_predictions_if_applicable) が記録の失敗と無関係に
    動くことを検証できるようにする。
    """

    def add_by_being(self, being_id, pending):
        raise RuntimeError('boom-pending-add')

def _build_pending_prediction_sidecar_fixture(*, player_id: int=7):
    """約束の記録 (pending_prediction) と清算 (pending_resolution) の両方を

    同じ chunk で LLM に返させるための一式を組み立てる。

    - LLM 応答に ``pending_prediction`` (新しい約束) と ``pending_resolutions``
      (既存約束 "p1" への fulfilled 判定) を両方含める
    - encoding_input.active_pending_predictions に既存約束 "p1" を乗せておく
      (清算対象として正規化されるために必要)
    """
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(occurred_at=t, action_summary='カイトと話した', result_summary='約束を交わした', tool_name='interact', success=True)
    existing_pending = PendingPrediction(pending_id='p1', text='約束-p1', resolution_cues=('spot:1',), tick_from=1, tick_to=50, origin_episode_id='ep-origin', created_tick=1)
    enc = build_chunk_encoding_input(PlayerId(player_id), (), (act,), active_pending_predictions=(existing_pending,))
    (being_id, resolver, world_id) = _provision_scheduler(player_id)
    draft = ChunkEpisodeDraftBuilder().build(enc, being_id=being_id)
    port = _StubPort(returns={'interpreted': 'I', 'recall_text': 'R', 'pending_prediction': {'text': '夕方に木の下でカイトと交換する', 'resolution_cues': ['player:カイト'], 'tick_offset_from': 2, 'tick_offset_to': 6}, 'pending_resolutions': [{'pending_id': 'p1', 'verdict': 'fulfilled'}]})
    service = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
    return (enc, draft, being_id, resolver, world_id, service, existing_pending)

class TestInlineSchedulerPendingPredictionSidecarIsolation:
    """約束の記録経路が失敗しても、補完自体の成否や清算の実行が正しく報告される。"""

    def test_failure_failed_filled_trace_episode_merged_saved_2(self) -> None:
        """約束の記録が失敗しても FAILED ではなく FILLED trace になり episode はmergedで保存される。"""
        (enc, draft, being_id, resolver, world_id, service, existing_pending) = _build_pending_prediction_sidecar_fixture()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        pending_store = _RaisingOnAddPendingPredictionStore()
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = InlineEpisodicSubjectiveScheduler(service, store, trace_recorder_provider=lambda : recorder, current_tick_provider=lambda : 10, pending_prediction_store=pending_store, pending_prediction_enabled=True)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        filled = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FILLED]
        assert failed == [], '約束の記録の失敗が補完失敗と誤報告されてはいけない'
        assert len(filled) == 1
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.interpreted == 'I'

    def test_failure_same_chunk_line_2(self) -> None:
        """記録 (add) の失敗が清算 (resolve) を巻き添えにしないことを保証する。"""
        (enc, draft, being_id, resolver, world_id, service, existing_pending) = _build_pending_prediction_sidecar_fixture()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        pending_store = _RaisingOnAddPendingPredictionStore()
        pending_store.replace_all_by_being(being_id, [existing_pending])
        scheduler = InlineEpisodicSubjectiveScheduler(service, store, current_tick_provider=lambda : 10, pending_prediction_store=pending_store, pending_prediction_enabled=True)
        scheduler.submit(draft, persona_text='', encoding_input=enc)
        remaining = pending_store.list_all_by_being(being_id)
        assert remaining == [], '約束の記録が失敗しても、同じ chunk の清算 (resolve) は独立して 実行されるべき'

class TestThreadPoolSchedulerPendingPredictionSidecarIsolation:
    """ThreadPool 版の ``_worker`` にも Inline と同じ分離が適用されていること。"""

    def test_failure_failed_filled_trace_episode_merged_saved(self) -> None:
        """約束の記録が失敗しても FAILED ではなく FILLED trace になり episode はmergedで保存される。"""
        (enc, draft, being_id, resolver, world_id, service, existing_pending) = _build_pending_prediction_sidecar_fixture()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        pending_store = _RaisingOnAddPendingPredictionStore()
        recorder = NullTraceRecorder()
        events = _capture(recorder)
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(service, store, max_workers=1, trace_recorder_provider=lambda : recorder, current_tick_provider=lambda : 10, pending_prediction_store=pending_store, pending_prediction_enabled=True)
        try:
            scheduler.submit(draft, persona_text='', encoding_input=enc)
            scheduler.shutdown(timeout=5.0)
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        failed = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FAILED]
        filled = [e for e in events if e.kind == TraceEventKind.EPISODIC_SUBJECTIVE_FILLED]
        assert failed == [], '約束の記録の失敗が補完失敗と誤報告されてはいけない'
        assert len(filled) == 1
        ep_after = store.get_by_being(being_id, draft.episode_id)
        assert ep_after is not None
        assert ep_after.interpreted == 'I'

    def test_failure_same_chunk_line(self) -> None:
        """約束の記録が失敗しても同じchunkの清算は実行される。"""
        (enc, draft, being_id, resolver, world_id, service, existing_pending) = _build_pending_prediction_sidecar_fixture()
        store = InMemorySubjectiveEpisodeStore()
        store.put_by_being(being_id, draft)
        pending_store = _RaisingOnAddPendingPredictionStore()
        pending_store.replace_all_by_being(being_id, [existing_pending])
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(service, store, max_workers=1, current_tick_provider=lambda : 10, pending_prediction_store=pending_store, pending_prediction_enabled=True)
        try:
            scheduler.submit(draft, persona_text='', encoding_input=enc)
            scheduler.shutdown(timeout=5.0)
        except Exception:
            scheduler.shutdown(timeout=2.0)
            raise
        remaining = pending_store.list_all_by_being(being_id)
        assert remaining == [], '約束の記録が失敗しても、同じ chunk の清算 (resolve) は独立して 実行されるべき'
