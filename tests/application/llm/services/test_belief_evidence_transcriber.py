"""BeliefEvidenceTranscriber の転記条件・trace 出力を保証する。

U2 (証拠台帳統一設計 §2 U2): 転記条件は「prediction_error が非 None」だけ。
それ以外の判定 (文字列一致カウンタ等) は作らない。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from tests.memory_turn_helpers import ZERO_TURN, FixedMemoryTurnReader

from ai_rpg_world.application.llm.services.belief_evidence_transcriber import BeliefEvidenceTranscriber
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import BeliefEvidenceSourceKind


def _episode(**overrides) -> SubjectiveEpisode:
    base = dict(episode_id='ep-1', player_id=1, occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc), game_time_label=None, source=EpisodeSource(event_ids=('evt-1',)), location=EpisodeLocation(spot_id=3), action=EpisodeAction(tool_name='explore'), who=(), what='w', why=None, observed='o', expected='何か見つかるはず', outcome='ok', prediction_error=None, felt=None, interpreted=None, cues=())
    base.update(overrides)
    if 'being_id' not in overrides:
        base['being_id'] = BeingId(f"being_w1_p{base['player_id']}")
    return SubjectiveEpisode(**base)

def _capture_trace(recorder: NullTraceRecorder) -> list:
    """NullTraceRecorder.record を wrap して返り値の TraceEvent を capture する。

    ``test_episodic_trace_emission.py`` と同じ規約 (専用の in-memory
    recorder クラスは作らず、NullTraceRecorder の戻り値を横取りする)。
    """
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev
    recorder.record = wrapper
    return captured

class TestBeliefEvidenceTranscriberTick:

    def test_tick_comes_from_current_tick_provider(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, current_tick_provider=lambda : 42, memory_turn_reader=ZERO_TURN)
        being_id = BeingId('being-1')
        transcriber.record_pending_resolution(being_id, _episode(), _pending_for_resolution(), verdict='broken')
        assert buffer_store.list_all_by_being(being_id)[0].tick == 42

    def test_tick_provider_exception_falls_back_None(self) -> None:
        """current_tick_provider が例外を投げても転記本体は止めない。"""

        def _raising() -> int:
            raise RuntimeError('boom')
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, current_tick_provider=_raising, memory_turn_reader=ZERO_TURN)
        being_id = BeingId('being-1')
        result = transcriber.record_pending_resolution(being_id, _episode(), _pending_for_resolution(), verdict='broken')
        assert result is not None
        assert buffer_store.list_all_by_being(being_id)[0].tick is None

class TestBeliefEvidenceTranscriberTrace:

    def test_emits_belief_evidence_trace_event(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = BeliefEvidenceTranscriber(buffer_store, trace_recorder_provider=lambda : recorder, current_tick_provider=lambda : 5, memory_turn_reader=ZERO_TURN)
        being_id = BeingId('being-1')
        transcriber.record_pending_resolution(being_id, _episode(), _pending_for_resolution(), verdict='broken')
        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert len(events) == 1
        payload = events[0].payload
        assert payload['being_id'] == 'being-1'
        assert payload['source_kind'] == 'pending_resolution'
        assert payload['cue_signature'] == 'player:カイト'
        assert payload['episode_ids'] == ['ep-1']
        assert events[0].tick == 5

    def test_trace_recorder_provider_is_safe(self) -> None:
        """trace_recorder_provider 未注入でも転記自体は成功する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        being_id = BeingId('being-1')
        result = transcriber.record_pending_resolution(being_id, _episode(), _pending_for_resolution(), verdict='broken')
        assert result is not None


class TestBeliefEvidenceTranscriberTypeGuards:

    def test_rejects_non_being_id(self) -> None:
        transcriber = BeliefEvidenceTranscriber(InMemoryBeliefEvidenceBufferStore(), memory_turn_reader=ZERO_TURN)
        with pytest.raises(TypeError):
            transcriber.record_pending_resolution('being-1', _episode(), _pending_for_resolution(), verdict='broken')

    def test_rejects_non_episode(self) -> None:
        transcriber = BeliefEvidenceTranscriber(InMemoryBeliefEvidenceBufferStore(), memory_turn_reader=ZERO_TURN)
        with pytest.raises(TypeError):
            transcriber.record_pending_resolution(BeingId('being-1'), 'not-an-episode', _pending_for_resolution(), verdict='broken')

    def test_rejects_non_repository_buffer_store(self) -> None:
        with pytest.raises(TypeError):
            BeliefEvidenceTranscriber(object(), memory_turn_reader=ZERO_TURN)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import PendingPrediction


def _pending_for_resolution(cues=('spot:3', 'player:カイト'), *, kind='promise', text='夕方に木の下でカイトと会う') -> PendingPrediction:
    return PendingPrediction(pending_id='pending-1', text=text, resolution_cues=tuple(cues), tick_from=10, tick_to=20, origin_episode_id='ep-origin', created_tick=10, kind=kind)

class TestBeliefEvidenceTranscriberPendingResolution:
    """record_pending_resolution が履行/破棄を PENDING_RESOLUTION に転記する (U10b)。"""

    def test_fulfilled_records_low_support(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        being_id = BeingId('being-1')
        ev = transcriber.record_pending_resolution(being_id, _episode(), _pending_for_resolution(), verdict='fulfilled')
        assert ev is not None
        assert ev.source_kind is BeliefEvidenceSourceKind.PENDING_RESOLUTION
        assert ev.salience == 'low'
        assert '果たされた' in ev.text
        assert ev.cue_signature == 'player:カイト'
        assert buffer_store.list_all_by_being(being_id) == [ev]

    def test_broken_records_high_contradiction(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        being_id = BeingId('being-1')
        ev = transcriber.record_pending_resolution(being_id, _episode(), _pending_for_resolution(), verdict='broken')
        assert ev.salience == 'high'
        assert '破られた' in ev.text

    def test_cue_signature_falls_back_first_cue_without_player(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        being_id = BeingId('being-1')
        ev = transcriber.record_pending_resolution(being_id, _episode(), _pending_for_resolution(cues=('spot:9',)), verdict='fulfilled')
        assert ev.cue_signature == 'spot:9'

    def test_invalid_verdict_raises(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        with pytest.raises(ValueError):
            transcriber.record_pending_resolution(BeingId('being-1'), _episode(), _pending_for_resolution(), verdict='maybe')

    def test_plan_kind_fulfilled_uses_mikomi_wording(self) -> None:
        """P11: plan (方針の見込み) の履行は「見込み『…』は当たった」文面。

        salience は verdict 由来で promise と同じ (fulfilled=low)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        plan = _pending_for_resolution(cues=('spot:3',), kind='plan', text='浜を探索すれば山頂への道が分かるはず')
        ev = transcriber.record_pending_resolution(BeingId('being-1'), _episode(), plan, verdict='fulfilled')
        assert '見込み' in ev.text
        assert '当たった' in ev.text
        assert '約束' not in ev.text
        assert ev.salience == 'low'

    def test_plan_kind_broken_uses_mikomi_wording_high_salience(self) -> None:
        """P11: plan の破れは「見込み『…』は外れた」= 方針レベルの予測誤差。

        破れは salience=high (即時固着候補)。有害 belief の反証に流れるのが狙い。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, memory_turn_reader=ZERO_TURN)
        plan = _pending_for_resolution(cues=('spot:3',), kind='plan', text='浜を探索すれば山頂への道が分かるはず')
        ev = transcriber.record_pending_resolution(BeingId('being-1'), _episode(), plan, verdict='broken')
        assert '見込み' in ev.text
        assert '外れた' in ev.text
        assert ev.salience == 'high'

class TestBeliefEvidenceTranscriberObservedTurn:
    """転記したすべての証拠に、転記したときの記憶のターン数が残ることを保証する (#1452)。"""

    @staticmethod
    def _transcriber(buffer_store, turn: int, **kwargs) -> BeliefEvidenceTranscriber:
        return BeliefEvidenceTranscriber(
            buffer_store, memory_turn_reader=FixedMemoryTurnReader(turn), **kwargs
        )

    def test_turn_is_read_for_the_being_that_observed(self) -> None:
        """ターン数は観測した Being のものを読む。別の Being の歩みを証拠に付けない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        rio, noa = BeingId('being-rio'), BeingId('being-noa')
        transcriber = BeliefEvidenceTranscriber(
            buffer_store,
            memory_turn_reader=FixedMemoryTurnReader(by_being={rio: 3, noa: 40}),
        )

        ev = transcriber.record_pending_resolution(noa, _episode(), _pending_for_resolution(), verdict='broken')

        assert ev is not None
        assert ev.observed_turn == 40

    def test_pending_resolution_evidence_carries_current_memory_turn(self) -> None:
        """約束の清算の証拠にも、転記したときの記憶のターン数 21 が残る。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = self._transcriber(buffer_store, 21)

        ev = transcriber.record_pending_resolution(
            BeingId('being-1'), _episode(), _pending_for_resolution(), verdict='broken'
        )

        assert ev is not None
        assert ev.observed_turn == 21

    def test_memory_turn_reader_is_required(self) -> None:
        """memory_turn_reader を渡さずに作ると TypeError になる。ターン数の無い証拠を作る経路を残さない。"""
        with pytest.raises(TypeError):
            BeliefEvidenceTranscriber(InMemoryBeliefEvidenceBufferStore())  # type: ignore[call-arg]
