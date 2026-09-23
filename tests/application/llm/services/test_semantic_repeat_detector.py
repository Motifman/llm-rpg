"""意味上の繰り返しを型付き判断に問う検出器の仕様 (#1412)。

完全一致の検出は `(tool 名, 引数の fingerprint)` が揃わないと数えない。言い直しや
呼び名を変えた同じ失敗は、直近 K 件の行動と結果を材料に「手段を変えずに同じことを
試し続けているか」を問う。件数はコードが持ち、判断には数えさせない。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.loop_guard_detectors import (
    RecordedAction,
    SemanticRepeat,
)
from ai_rpg_world.application.llm.services.semantic_repeat_detector import (
    QUESTION_NAME,
    SemanticRepeatDetector,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

GAREN, YUNO = PlayerId(1), PlayerId(2)
NAMES = {1: "ガレン", 2: "ユノ"}


class _Port(ITypedJudgmentPort):
    def __init__(self, probability: float = 0.5) -> None:
        self.probability = probability
        self.calls: list[tuple[Any, Mapping[str, Any]]] = []

    def judge(self, state, questions):
        self.calls.append((state, dict(questions)))
        return {
            q: JudgmentResult(
                value=self.probability, probabilities={}, confidence=None,
                source=JudgmentSource.JEV, latency_ms=12.0,
            )
            for q in questions
        }


class _FailingPort(ITypedJudgmentPort):
    def judge(self, state, questions):
        raise TypedJudgmentUnavailableException(
            "down", error_code="TYPED_JUDGMENT_TRANSPORT_FAILED"
        )


class _Recorder:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, kind, **payload) -> None:
        assert kind is TraceEventKind.TYPED_JUDGMENT
        self.events.append(payload)


def _detector(
    port: ITypedJudgmentPort,
    *,
    window: int = 3,
    threshold: float = 0.8,
    recorder: _Recorder | None = None,
) -> SemanticRepeatDetector:
    return SemanticRepeatDetector(
        port,
        player_name_resolver=lambda pid: NAMES[int(pid.value)],
        window_size=window,
        threshold=threshold,
        trace_recorder_provider=(lambda: recorder) if recorder is not None else None,
    )


def _action(player: PlayerId, content: str, *, tick: int = 53) -> RecordedAction:
    return RecordedAction(
        player_key=int(player.value),
        tool_name="speak",
        fingerprint=build_argument_fingerprint({"channel": "say", "content": content}),
        success=True,
        error_code=None,
        tick=tick,
        result_summary="（2 名に届いた）",
    )


def _offer(detector: SemanticRepeatDetector, player: PlayerId = GAREN, n: int = 1, **kw):
    signal = None
    for i in range(n):
        signal = detector.observe(
            _action(player, f"ユノ、麦束と薬草を交換しないか (言い直し {i})"), **kw
        )
    return signal


class TestTheDetectorAsksOnlyWithAFullWindow:
    """直近の行動が K 件そろったときだけ、1 回だけ問うことを保証する。"""

    def test_fewer_than_k_actions_do_not_reach_the_judgment_port(self) -> None:
        """直近の行動が K 件に満たないとき、判断ポートを呼ばず signal も返さない。"""
        port = _Port(probability=0.99)
        detector = _detector(port, window=3)

        signal = _offer(detector, n=2)

        assert signal is None
        assert port.calls == []

    def test_a_full_window_is_asked_once_with_actions_oldest_first(self) -> None:
        """K 件そろうと、行動と結果を古い順に並べた state で 1 回だけ問う。"""
        port = _Port()
        detector = _detector(port, window=3)

        _offer(detector, n=3)

        assert len(port.calls) == 1
        state, questions = port.calls[0]
        assert [a["action"] for a in state["recent_actions"]] == [
            f"あなたは言った: 「ユノ、麦束と薬草を交換しないか (言い直し {i})」"
            for i in range(3)
        ]
        assert state["recent_actions"][0]["result"] == "（2 名に届いた）"
        assert state["recent_actions"][0]["succeeded"] is True
        assert list(questions) == [QUESTION_NAME]
        assert isinstance(questions[QUESTION_NAME], NoulQuestion)

    def test_the_window_keeps_only_the_latest_k_actions(self) -> None:
        """K 件を超えたら古い行動を落とし、state には直近 K 件だけが入る。"""
        port = _Port(probability=0.1)
        detector = _detector(port, window=3)

        _offer(detector, n=4)

        state, _ = port.calls[-1]
        assert len(state["recent_actions"]) == 3
        assert state["recent_actions"][0]["action"].endswith("(言い直し 1)」")

    def test_each_player_has_an_independent_window(self) -> None:
        """他人の行動は窓に混ざらない。2 人が 2 件ずつでは K=3 に届かない。"""
        port = _Port()
        detector = _detector(port, window=3)

        _offer(detector, GAREN, n=2)
        _offer(detector, YUNO, n=2)

        assert port.calls == []


class TestTheThresholdDecidesTheSignal:
    """確率が閾値以上のときだけ signal を返すことを保証する。"""

    def test_a_probability_at_or_above_the_threshold_returns_a_signal(self) -> None:
        """確率が閾値以上なら、件数 K と最後の行動を持つ signal を返す。"""
        detector = _detector(_Port(probability=0.8), window=3, threshold=0.8)

        signal = _offer(detector, n=3)

        assert isinstance(signal, SemanticRepeat)
        assert signal.count == 3
        assert signal.probability == pytest.approx(0.8)
        assert signal.tool_name == "speak"
        assert "言い直し 2" in signal.fingerprint
        assert signal.tick == 53

    def test_a_probability_below_the_threshold_returns_nothing(self) -> None:
        """確率が閾値未満なら signal を返さない。"""
        detector = _detector(_Port(probability=0.79), window=3, threshold=0.8)

        assert _offer(detector, n=3) is None

    def test_an_unavailable_judgment_returns_nothing(self) -> None:
        """判断ポートが例外を投げたとき、signal を返さない (判断が無いことを判断の結果にしない)。"""
        detector = _detector(_FailingPort(), window=3)

        assert _offer(detector, n=3) is None

    def test_after_a_signal_the_window_must_fill_again_before_asking(self) -> None:
        """signal を出したら窓を空にし、新しい行動が K 件溜まるまで問わない。"""
        port = _Port(probability=0.95)
        detector = _detector(port, window=3)
        _offer(detector, n=3)

        _offer(detector, n=2)
        assert len(port.calls) == 1

        assert _offer(detector, n=1) is not None
        assert len(port.calls) == 2

    def test_a_rejected_window_slides_and_is_asked_again_next_turn(self) -> None:
        """閾値未満なら窓は空にせず、次の行動で 1 件ずれた窓をまた問う。"""
        port = _Port(probability=0.1)
        detector = _detector(port, window=3)

        _offer(detector, n=4)

        assert len(port.calls) == 2


class TestTheWindowIsBuiltFromTheRecordedAction:
    """窓の要約を、評価に使ったのと同じ形で記録から作ることを保証する。"""

    def test_the_summary_carries_what_was_said_and_hides_the_inner_thought(self) -> None:
        """発言は内容つきの要約になり、fingerprint から落ちない引数の内心は出ない。"""
        port = _Port()
        detector = _detector(port, window=2)
        action = RecordedAction(
            player_key=1, tool_name="speak",
            fingerprint=build_argument_fingerprint(
                {"channel": "say", "content": "薬草と交換したい", "inner_thought": "焦っている"}
            ),
            success=True, error_code=None, tick=50, result_summary="（2 名に届いた）",
        )

        detector.observe(action)
        detector.observe(action)

        state, _ = port.calls[0]
        assert state["recent_actions"][0]["action"] == "あなたは言った: 「薬草と交換したい」"
        assert "焦っている" not in str(state)

    def test_a_missing_result_summary_is_passed_as_an_empty_result(self) -> None:
        """結果の文が無い記録は空の結果として渡し、窓から落とさない。"""
        port = _Port()
        detector = _detector(port, window=2)
        action = RecordedAction(
            player_key=1, tool_name="wait", fingerprint=build_argument_fingerprint({}),
            success=True, error_code=None, tick=50,
        )

        detector.observe(action)
        detector.observe(action)

        state, _ = port.calls[0]
        assert [a["result"] for a in state["recent_actions"]] == ["", ""]


class TestTheStateCarriesNoGoal:
    """state に本人の目的や整数 ID を入れないことを保証する (design_decisions #222)。"""

    def test_the_state_has_only_the_actor_name_and_recent_actions(self) -> None:
        """state は行為者の名前と直近の行動だけを持ち、目的・内心・ID を持たない。"""
        port = _Port()
        detector = _detector(port, window=3)

        _offer(detector, n=3)

        state, _ = port.calls[0]
        assert set(state) == {"actor", "recent_actions"}
        assert state["actor"] == "ガレン"
        assert set(state["recent_actions"][0]) == {"action", "result", "succeeded"}


class TestEveryQuestionLeavesATrace:
    """問うたびに TYPED_JUDGMENT を 1 件残し、出さなかった分も読めることを保証する。"""

    def test_a_judged_window_is_traced_with_probability_threshold_and_window(self) -> None:
        """確率・閾値・採否・渡した窓・完全一致の発火有無を 1 件に残す。"""
        recorder = _Recorder()
        detector = _detector(_Port(probability=0.3), window=3, threshold=0.8, recorder=recorder)
        _offer(detector, n=2)

        _offer(detector, n=1, exact_match_fired=True)

        assert len(recorder.events) == 1
        event = recorder.events[0]
        assert event["question"] == QUESTION_NAME
        assert event["tick"] == 53
        assert event["player_id"] == 1
        assert event["probability"] == pytest.approx(0.3)
        assert event["threshold"] == pytest.approx(0.8)
        assert event["accepted"] is False
        assert event["exact_match_fired"] is True
        assert len(event["window"]) == 3
        assert event["unavailable_reason"] is None

    def test_an_unavailable_judgment_is_traced_with_its_reason(self) -> None:
        """判断が得られなかったとき、trace に unavailable_reason を残す。"""
        recorder = _Recorder()
        detector = _detector(_FailingPort(), window=3, recorder=recorder)

        _offer(detector, n=3)

        assert len(recorder.events) == 1
        assert recorder.events[0]["unavailable_reason"] == "TYPED_JUDGMENT_TRANSPORT_FAILED"
        assert recorder.events[0]["probability"] is None
        assert recorder.events[0]["accepted"] is False

    def test_a_window_not_yet_full_leaves_no_trace(self) -> None:
        """問わなかった回は TYPED_JUDGMENT を残さない。問うた回数と trace の件数が一致する。"""
        recorder = _Recorder()
        detector = _detector(_Port(), window=3, recorder=recorder)

        _offer(detector, n=2)

        assert recorder.events == []


class TestConstruction:
    """閾値と窓の大きさの範囲外は構築時に落ちることを保証する。"""

    @pytest.mark.parametrize("threshold", [0.0, -0.1, 1.01])
    def test_a_threshold_outside_zero_to_one_is_rejected(self, threshold: float) -> None:
        """閾値が (0, 1] の外なら ValueError。"""
        with pytest.raises(ValueError):
            _detector(_Port(), threshold=threshold)

    def test_a_window_smaller_than_two_is_rejected(self) -> None:
        """K が 2 未満では繰り返しを材料にできないので ValueError。"""
        with pytest.raises(ValueError):
            _detector(_Port(), window=1)


class _BrokenPort(ITypedJudgmentPort):
    def judge(self, state, questions):
        raise RuntimeError("adapter bug")


class TestAnExactMatchResetsTheWindow:
    """完全一致の検出が発火した行動を最後に、窓を空にすることを保証する。"""

    def test_after_an_exact_match_the_window_must_fill_again_before_asking(self) -> None:
        """exact_match_fired=True の行動のあとは、新しい行動が K 件溜まるまで問わない。"""
        port = _Port(probability=0.5)
        detector = _detector(port, window=3)
        _offer(detector, n=2)
        _offer(detector, n=1, exact_match_fired=True)
        asked_before = len(port.calls)

        _offer(detector, n=2)

        assert len(port.calls) == asked_before


class TestGoalFieldsDoNotReachTheState:
    """本人の目的を、判断の材料に入れないことを保証する (design_decisions #222)。"""

    def test_goal_fields_riding_on_an_unlisted_tool_do_not_reach_the_state(self) -> None:
        """要約の表に無い tool に goal_update / goal_outcome が付いていても、state に出さない。"""
        port = _Port()
        detector = _detector(port, window=2)
        action = RecordedAction(
            player_key=1, tool_name="memory_recall_episodes",
            fingerprint=build_argument_fingerprint(
                {"query": "薬草", "goal_update": "ユノから薬草を手に入れる", "goal_outcome": None}
            ),
            success=True, error_code=None, tick=50, result_summary="思い出せなかった",
        )

        detector.observe(action)
        detector.observe(action)

        state, _ = port.calls[0]
        assert "ユノから薬草を手に入れる" not in str(state)
        assert "goal_outcome" not in str(state)
        assert "薬草" in state["recent_actions"][0]["action"]


class TestAnUnexpectedErrorIsTreatedAsUnavailable:
    """判断ポートの想定外の例外を外へ出さず、判断不能として扱うことを保証する。"""

    def test_an_unexpected_error_returns_nothing_and_is_traced(self) -> None:
        """判断ポートが RuntimeError を投げても signal を返さず、trace に UNEXPECTED_ERROR を残す。"""
        recorder = _Recorder()
        detector = _detector(_BrokenPort(), recorder=recorder)

        assert _offer(detector, n=3) is None
        [event] = recorder.events
        assert event["unavailable_reason"] == "UNEXPECTED_ERROR"
        assert event["accepted"] is False


class TestTheTracedWindowIsWhatWasAsked:
    """trace に残す窓と、判断に渡した窓が同じであることを保証する。"""

    def test_a_long_result_is_cut_the_same_way_in_state_and_trace(self) -> None:
        """長い結果の文は state でも切り詰め、trace の窓は state の窓と一致する。"""
        port = _Port()
        recorder = _Recorder()
        detector = _detector(port, window=2, recorder=recorder)
        action = RecordedAction(
            player_key=1, tool_name="wait", fingerprint=build_argument_fingerprint({}),
            success=True, error_code=None, tick=50, result_summary="長" * 5000,
        )

        detector.observe(action)
        detector.observe(action)

        state, _ = port.calls[0]
        assert len(state["recent_actions"][0]["result"]) < 5000
        assert recorder.events[0]["window"] == state["recent_actions"]
