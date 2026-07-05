"""BeliefEvidenceTranscriber の転記条件・trace 出力を保証する。

U2 (証拠台帳統一設計 §2 U2): 転記条件は「prediction_error が非 None」だけ。
それ以外の判定 (文字列一致カウンタ等) は作らない。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
    BeliefEvidenceTranscriber,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


def _episode(**overrides) -> SubjectiveEpisode:
    base = dict(
        episode_id="ep-1",
        player_id=1,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=3),
        action=EpisodeAction(tool_name="explore"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected="何か見つかるはず",
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
    )
    base.update(overrides)
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

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


class TestBeliefEvidenceTranscriberRecordCondition:
    def test_prediction_error_none_does_not_record(self) -> None:
        """転記条件: prediction_error が None なら evidence を積まない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(being_id, _episode(prediction_error=None))

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_prediction_error_non_none_records_one_evidence(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id, _episode(prediction_error="何もなかった")
        )

        assert result is not None
        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].text == "何もなかった"
        assert rows[0].episode_ids == ("ep-1",)
        assert rows[0].cue_signature == "tool:explore|spot:3"

    def test_records_are_scoped_per_being(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_a = BeingId("being-a")
        being_b = BeingId("being-b")

        transcriber.record_if_applicable(
            being_a, _episode(prediction_error="外れた")
        )

        assert len(buffer_store.list_all_by_being(being_a)) == 1
        assert buffer_store.list_all_by_being(being_b) == []


class TestBeliefEvidenceTranscriberSalience:
    """U6 (予測誤差統一設計 / salience): episode.salience がそのまま
    evidence.salience に転記されること。SALIENCE_STRUCTURED_FAILURE_ENABLED
    が OFF のとき episode.salience は常に "low" (chunk 主観補完 service 側の
    保証) なので、本テストの "low" 系は導入前の固定挙動と一致する。"""

    def test_episode_low_salience_becomes_evidence_low_salience(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた", salience="low")
        )

        assert buffer_store.list_all_by_being(being_id)[0].salience == "low"

    def test_episode_high_salience_becomes_evidence_high_salience(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="大ダメージを受けた", salience="high")
        )

        assert buffer_store.list_all_by_being(being_id)[0].salience == "high"


class TestBeliefEvidenceTranscriberTick:
    def test_tick_comes_from_current_tick_provider(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, current_tick_provider=lambda: 42
        )
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた")
        )

        assert buffer_store.list_all_by_being(being_id)[0].tick == 42

    def test_tick_provider_exception_falls_back_to_none(self) -> None:
        """current_tick_provider が例外を投げても転記本体は止めない。"""

        def _raising() -> int:
            raise RuntimeError("boom")

        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, current_tick_provider=_raising
        )
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた")
        )

        assert result is not None
        assert buffer_store.list_all_by_being(being_id)[0].tick is None


class TestBeliefEvidenceTranscriberTrace:
    def test_emits_belief_evidence_trace_event(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = BeliefEvidenceTranscriber(
            buffer_store,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 5,
        )
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="想定外だった")
        )

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert len(events) == 1
        payload = events[0].payload
        assert payload["being_id"] == "being-1"
        assert payload["source_kind"] == "prediction_error"
        assert payload["cue_signature"] == "tool:explore|spot:3"
        assert payload["episode_ids"] == ["ep-1"]
        assert events[0].tick == 5

    def test_no_trace_recorder_provider_is_safe(self) -> None:
        """trace_recorder_provider 未注入でも転記自体は成功する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id, _episode(prediction_error="想定外だった")
        )

        assert result is not None

    def test_no_evidence_means_no_trace(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, trace_recorder_provider=lambda: recorder
        )
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(being_id, _episode(prediction_error=None))

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert events == []


class TestBeliefEvidenceTranscriberAttribution:
    """U4 (予測誤差統一設計 部品3): in_context_belief_ids の添付と CONFIRMATION 転記。"""

    def test_prediction_error_evidence_に_in_context_belief_ids_が添付される(
        self,
    ) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error="外れた"),
            in_context_belief_ids=("sem-1", "sem-2"),
            had_expected_result=True,
        )

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind == BeliefEvidenceSourceKind.PREDICTION_ERROR
        assert rows[0].in_context_belief_ids == ("sem-1", "sem-2")

    def test_prediction_error_None_かつ_in_context_belief_あり_かつ_expected_result_ありなら_CONFIRMATION(
        self,
    ) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None, expected="何か見つかるはず"),
            in_context_belief_ids=("sem-1",),
            had_expected_result=True,
        )

        assert result is not None
        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind == BeliefEvidenceSourceKind.CONFIRMATION
        assert rows[0].in_context_belief_ids == ("sem-1",)
        assert rows[0].text == "予測が当たった: 何か見つかるはず"

    def test_prediction_error_None_かつ_in_context_belief_無しなら何も積まない(
        self,
    ) -> None:
        """水増しガード: in-context belief が無いターンでは CONFIRMATION を作らない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None),
            in_context_belief_ids=(),
            had_expected_result=True,
        )

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_prediction_error_None_かつ_expected_result_無しターンなら何も積まない(
        self,
    ) -> None:
        """水増しガード: 何も予測せず行動しただけのターンでは CONFIRMATION を作らない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None),
            in_context_belief_ids=("sem-1",),
            had_expected_result=False,
        )

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_flag_OFF相当_呼び出し側が空を渡せば導入前と一致する(self) -> None:
        """呼び出し側 (coordinator/scheduler) が flag OFF のとき常に空/False を
        渡す設計 (= transcriber 自身は flag を知らない) の安全性を確認する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        # prediction_error あり: in_context_belief_ids は空のまま添付される。
        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた")
        )
        # prediction_error 無し: CONFIRMATION も生まれない。
        transcriber.record_if_applicable(being_id, _episode(prediction_error=None))

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind == BeliefEvidenceSourceKind.PREDICTION_ERROR
        assert rows[0].in_context_belief_ids == ()


class TestComputeChunkAttribution:
    """U4: chunk を構成する action 群から attribution 用の値を計算する純関数。"""

    def test_複数_action_の_in_context_belief_ids_を重複排除して和集合する(self) -> None:
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            compute_chunk_attribution,
        )

        class _Action:
            def __init__(self, in_context_belief_ids=(), expected_result=None):
                self.in_context_belief_ids = in_context_belief_ids
                self.expected_result = expected_result

        actions = [
            _Action(in_context_belief_ids=("sem-1", "sem-2")),
            _Action(in_context_belief_ids=("sem-2", "sem-3"), expected_result="X"),
        ]

        belief_ids, had_expected_result = compute_chunk_attribution(actions)

        assert belief_ids == ("sem-1", "sem-2", "sem-3")
        assert had_expected_result is True

    def test_action群が空なら空タプルとFalseを返す(self) -> None:
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            compute_chunk_attribution,
        )

        belief_ids, had_expected_result = compute_chunk_attribution([])

        assert belief_ids == ()
        assert had_expected_result is False


class TestBeliefEvidenceTranscriberTypeGuards:
    def test_rejects_non_being_id(self) -> None:
        transcriber = BeliefEvidenceTranscriber(InMemoryBeliefEvidenceBufferStore())
        with pytest.raises(TypeError):
            transcriber.record_if_applicable("being-1", _episode())

    def test_rejects_non_episode(self) -> None:
        transcriber = BeliefEvidenceTranscriber(InMemoryBeliefEvidenceBufferStore())
        with pytest.raises(TypeError):
            transcriber.record_if_applicable(BeingId("being-1"), "not-an-episode")

    def test_rejects_non_repository_buffer_store(self) -> None:
        with pytest.raises(TypeError):
            BeliefEvidenceTranscriber(object())
