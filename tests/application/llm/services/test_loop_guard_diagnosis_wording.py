from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.loop_diagnosis import (
    NONE_APPLICABLE_OPTION,
    QUESTION_NAME,
    LoopDiagnosis,
    RepeatReason,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_PID = PlayerId.create(4)
_TRAVEL = {"destination_label": "薬草の土手"}
_DIRECTIVES = ("別の行動", "以外の行動", "選ぶこと", "してはいけない", "切り替えること")


class _FixedPort(ITypedJudgmentPort):
    def __init__(
        self, value: str, *, probability: float = 0.9, confidence: float | None = 0.9
    ) -> None:
        self.value = value
        self.probability = probability
        self.confidence = confidence
        self.states: list[Any] = []

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.states.append(state)
        return {
            QUESTION_NAME: JudgmentResult(
                value=self.value,
                probabilities={self.value: self.probability},
                confidence=self.confidence,
                source=JudgmentSource.STUB,
                latency_ms=2.0,
            )
        }


class _RaisingPort(ITypedJudgmentPort):
    def __init__(self) -> None:
        self.calls = 0

    def judge(self, state, questions):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise TypedJudgmentUnavailableException(
            "timeout", error_code="TYPED_JUDGMENT_TIMEOUT"
        )


class _BrokenPort(ITypedJudgmentPort):
    def judge(self, state, questions):  # type: ignore[no-untyped-def]
        raise RuntimeError("adapter bug")


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind, *, tick=None, player_id=None, **payload):  # type: ignore[no-untyped-def,override]
        self.calls.append((kind, {"tick": tick, "player_id": player_id, **payload}))
        return super().record(kind, tick=tick, player_id=player_id, **payload)

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [p for k, p in self.calls if k == kind]


class _Tick:
    def __init__(self) -> None:
        self.value = 10

    def __call__(self) -> int:
        return self.value


def _guard(
    port: ITypedJudgmentPort | None,
    *,
    buffer: DefaultObservationContextBuffer | None = None,
    recorder: _Recorder | None = None,
    tick: _Tick | None = None,
    location: str | None = "薬草の土手",
) -> ToolCallLoopGuardService:
    return ToolCallLoopGuardService(
        buffer if buffer is not None else DefaultObservationContextBuffer(),
        time_label_provider=lambda: "深夜 2:05",
        clock=lambda: datetime(2026, 1, 1),
        trace_recorder=recorder,
        current_tick_provider=tick if tick is not None else _Tick(),
        loop_diagnosis=(
            LoopDiagnosis(port=port, min_confidence=0.7) if port is not None else None
        ),
        location_provider=lambda pid: location,
    )


def _travel_twice(guard: ToolCallLoopGuardService) -> None:
    guard.record_and_check(
        _PID, "travel_to", _TRAVEL, success=True, result_summary="薬草の土手へ移動しました。"
    )
    guard.record_and_check(
        _PID,
        "travel_to",
        _TRAVEL,
        success=False,
        error_code="INVALID_DESTINATION_LABEL",
        result_summary="移動先が見つかりません: 薬草の土手。",
    )


def _warnings(buffer: DefaultObservationContextBuffer) -> list[str]:
    return [
        e.output.prose
        for e in buffer.get_observations(_PID)
        if (e.output.structured or {}).get("loop_guard")
    ]


class TestWordingFollowsTheDiagnosedReason:
    """見立てた理由ごとに、警告の文面が命令ではなく事実を伝えることを保証する。"""

    def test_state_mistaken_tells_the_current_location_without_ordering_another_action(
        self,
    ) -> None:
        """「状態の取り違え」なら、観測は現在地「薬草の土手」を伝え、別の行動を選べという命令を含まない。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_FixedPort(RepeatReason.STATE_MISTAKEN.value), buffer=buffer)

        _travel_twice(guard)

        [prose] = _warnings(buffer)
        assert "いまの居場所は「薬草の土手」" in prose
        assert not any(d in prose for d in _DIRECTIVES)

    def test_waiting_still_emits_the_warning(self) -> None:
        """「待機」と見立てても、警告の観測は 1 件出る。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_FixedPort(RepeatReason.WAITING.value), buffer=buffer)

        for _ in range(3):
            guard.record_and_check(_PID, "wait", {}, success=True)

        assert len(_warnings(buffer)) == 1

    @pytest.mark.parametrize("reason", list(RepeatReason))
    def test_no_reason_wording_orders_the_agent(self, reason: RepeatReason) -> None:
        """どの理由の文面も、繰り返した行動の名前を含み、命令の言い回しを含まない。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_FixedPort(reason.value), buffer=buffer)

        _travel_twice(guard)

        [prose] = _warnings(buffer)
        assert "`travel_to`" in prose
        assert not any(d in prose for d in _DIRECTIVES)

    def test_missing_precondition_quotes_the_latest_failure(self) -> None:
        """「前提の欠けた再試行」なら、直近の失敗文をそのまま載せる。対処のヒントは指示を含むので載せない。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_FixedPort(RepeatReason.MISSING_PRECONDITION.value), buffer=buffer)

        _travel_twice(guard)

        [prose] = _warnings(buffer)
        assert "「移動先が見つかりません: 薬草の土手」" in prose


class TestFallingBackToTheCurrentWording:
    """見立てが採れないときは、見立てを入れない場合と同じ文面で警告を出すことを保証する。"""

    def _baseline(self) -> list[str]:
        buffer = DefaultObservationContextBuffer()
        _travel_twice(_guard(None, buffer=buffer))
        return _warnings(buffer)

    @pytest.mark.parametrize(
        "port",
        [
            _FixedPort(NONE_APPLICABLE_OPTION),
            _FixedPort(RepeatReason.WAITING.value, probability=0.5),
            _RaisingPort(),
        ],
        ids=["none_applicable", "below_threshold", "unavailable"],
    )
    def test_fallback_uses_the_same_prose_as_without_diagnosis(
        self, port: ITypedJudgmentPort
    ) -> None:
        """該当なし・閾値未満・例外のどれでも、観測の文面は見立てなしのときと一致する。"""
        buffer = DefaultObservationContextBuffer()

        _travel_twice(_guard(port, buffer=buffer))

        assert _warnings(buffer) == self._baseline()

    def test_unavailable_is_left_in_the_trace_with_the_error_code(self) -> None:
        """判断ポートが例外を投げたら、TYPED_JUDGMENT に unavailable と error_code が残る。"""
        recorder = _Recorder()

        _travel_twice(_guard(_RaisingPort(), recorder=recorder))

        [event] = recorder.of(TraceEventKind.TYPED_JUDGMENT)
        assert event["question"] == QUESTION_NAME
        assert event["fallback_reason"] == "unavailable"
        assert event["unavailable_reason"] == "TYPED_JUDGMENT_TIMEOUT"

    def test_an_unexpected_error_still_emits_the_current_warning(self) -> None:
        """判断ポートが想定外の例外を投げても、今の文面で警告を出し、UNEXPECTED_ERROR を trace に残す。"""
        buffer = DefaultObservationContextBuffer()
        recorder = _Recorder()

        _travel_twice(_guard(_BrokenPort(), buffer=buffer, recorder=recorder))

        assert _warnings(buffer) == self._baseline()
        [event] = recorder.of(TraceEventKind.TYPED_JUDGMENT)
        assert event["fallback_reason"] == "unavailable"
        assert event["unavailable_reason"] == "UNEXPECTED_ERROR"

    def test_without_diagnosis_no_typed_judgment_is_recorded(self) -> None:
        """見立てを入れないとき、TYPED_JUDGMENT は残らず、警告の trace に文面の区分も載らない。"""
        recorder = _Recorder()

        _travel_twice(_guard(None, recorder=recorder))

        assert recorder.of(TraceEventKind.TYPED_JUDGMENT) == []
        [warning] = recorder.of(TraceEventKind.LOOP_GUARD_WARNING)
        assert "wording" not in warning


class TestBothDetectorsAskForTheDiagnosis:
    """連続の同一行動と、離れた tick での同一失敗の両方で見立てを問うことを保証する。"""

    def test_cross_tick_failure_is_diagnosed(self) -> None:
        """同じ失敗が tick 10・12・14 に出て離れた tick の警告が出るとき、見立てを 1 回問い、その理由の文面になる。"""
        buffer = DefaultObservationContextBuffer()
        tick = _Tick()
        port = _FixedPort(RepeatReason.MISSING_PRECONDITION.value)
        guard = _guard(port, buffer=buffer, tick=tick)
        bake = {"action_name": "bake_bread", "target_label": "石窯"}

        for t in (10, 12, 14):
            tick.value = t
            guard.record_and_check(
                _PID,
                "interact",
                bake,
                success=False,
                error_code="INTERACTION_PRECONDITION_FAILED",
                result_summary="麦束がありません。",
            )
            guard.record_and_check(_PID, "wait", {}, success=True)

        assert len(port.states) == 1
        [prose] = _warnings(buffer)
        assert "「麦束がありません」" in prose
        assert not any(d in prose for d in _DIRECTIVES)


class TestTheTraceKeepsWhatTheJudgmentSaw:
    """TYPED_JUDGMENT に、見立てが見た state と採否が残ることを保証する。"""

    def test_trace_carries_probabilities_threshold_adoption_and_state(self) -> None:
        """採った見立ての trace は、確率・閾値・採否・渡した state を持ち、警告の trace に文面の区分が載る。"""
        recorder = _Recorder()
        port = _FixedPort(RepeatReason.STATE_MISTAKEN.value, probability=0.8)

        _travel_twice(_guard(port, recorder=recorder))

        [event] = recorder.of(TraceEventKind.TYPED_JUDGMENT)
        assert event["pattern"] == "streak"
        assert event["probabilities"] == {"state_mistaken": 0.8}
        assert event["min_confidence"] == 0.7
        assert event["accepted"] is True
        assert event["reason"] == "state_mistaken"
        assert event["fallback_reason"] is None
        assert event["state"] == port.states[0]
        [warning] = recorder.of(TraceEventKind.LOOP_GUARD_WARNING)
        assert warning["wording"] == "state_mistaken"


class TestTheStateHoldsOnlyWhatTheWorldShows:
    """見立てに渡す state が、直近の行動と結果・居場所・届いている観測だけでできていることを保証する。"""

    def test_state_has_recent_actions_location_and_observations_now(self) -> None:
        """state は繰り返した行動、結果つきの直近の行動、現在地、いま届いている観測の本文を持つ。"""
        buffer = DefaultObservationContextBuffer()
        buffer.append(
            _PID,
            ObservationEntry(
                occurred_at=datetime(2026, 1, 1),
                output=ObservationOutput(prose="カイが土手で草を摘んでいる。", structured={}),
            ),
        )
        port = _FixedPort(RepeatReason.STATE_MISTAKEN.value)

        _travel_twice(_guard(port, buffer=buffer))

        [state] = port.states
        assert state["repeated_action"] == "`travel_to`（対象: 薬草の土手）"
        assert state["recent_actions"] == [
            {
                "action": "`travel_to`（対象: 薬草の土手）",
                "succeeded": True,
                "result": "薬草の土手へ移動しました。",
            },
            {
                "action": "`travel_to`（対象: 薬草の土手）",
                "succeeded": False,
                "result": "移動先が見つかりません: 薬草の土手。",
            },
        ]
        assert state["current_location"] == "薬草の土手"
        assert state["observations_now"] == ["カイが土手で草を摘んでいる。"]

    def test_state_carries_no_player_id_and_no_goal(self) -> None:
        """state のどの値にも player_id の整数は入らず、目的や memo の項目も無い。"""
        port = _FixedPort(RepeatReason.STATE_MISTAKEN.value)

        _travel_twice(_guard(port))

        [state] = port.states
        assert set(state) <= {
            "repeated_action",
            "repetition",
            "recent_actions",
            "current_location",
            "observations_now",
        }
        assert not _contains_int(state)


def _contains_int(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, Mapping):
        return any(_contains_int(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_int(v) for v in value)
    return False


class TestTheStateCarriesWhatWasSaid:
    """発言の繰り返しを見分けられるよう、state の直近の行動に発言内容が載ることを保証する。"""

    def test_speech_content_appears_as_said_in_recent_actions(self) -> None:
        """同じ speak を 2 回続けると、state の直近の行動それぞれに said として発言内容が載る。"""
        port = _FixedPort(RepeatReason.UNANSWERED_REQUEST.value)
        guard = _guard(port)
        offer = {"channel": "say", "content": "ユノ、麦束と薬草を交換しないか？"}

        for _ in range(2):
            guard.record_and_check(
                _PID, "speak", offer, success=True, result_summary="（2 名に届いた）"
            )

        [state] = port.states
        assert [a.get("said") for a in state["recent_actions"]] == [
            "ユノ、麦束と薬草を交換しないか？"
        ] * 2

    def test_unanswered_request_counts_the_same_words_even_when_the_addressee_was_dropped(
        self,
    ) -> None:
        """1 回目だけ宛先つきで同じ内容を 3 回言うと、「返事待ちの再依頼」の文面は 3 回目と数える。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_FixedPort(RepeatReason.UNANSWERED_REQUEST.value), buffer=buffer)
        words = "ユノ、麦束と薬草を交換しないか？"

        guard.record_and_check(
            _PID, "speak", {"channel": "say", "content": words, "target_label": "ユノ"},
            success=True, result_summary="（2 名に届いた）",
        )
        for _ in range(2):
            guard.record_and_check(
                _PID, "speak", {"channel": "say", "content": words},
                success=True, result_summary="（2 名に届いた）",
            )

        [prose] = _warnings(buffer)
        assert "同じ内容を伝えたのは 3 回目" in prose
