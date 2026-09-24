"""意味上の繰り返しの検出器を、ループ警告の 3 つ目の検出器として合流させた仕様 (#1412)。

完全一致の検出が拾えない言い直しを、意味上の検出器が拾い、同じ警告の出し口から
観測を出す。同じ行動で完全一致の検出も発火したときは、観測を 1 件にまとめる。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.loop_diagnosis import (
    QUESTION_NAME as LOOP_DIAGNOSIS_QUESTION,
)
from ai_rpg_world.application.llm.services.loop_diagnosis import (
    LoopDiagnosis,
    RepeatReason,
)
from ai_rpg_world.application.llm.services.semantic_repeat_detector import (
    QUESTION_NAME as SEMANTIC_REPEAT_QUESTION,
)
from ai_rpg_world.application.llm.services.semantic_repeat_detector import (
    SemanticRepeatDetector,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_GAREN = PlayerId.create(1)
_DIRECTIVES = ("別の行動", "以外の行動", "選ぶこと", "してはいけない", "切り替えること")


class _Port(ITypedJudgmentPort):
    """質問の名前ごとに答えを返し、問われた質問を記録する。"""

    def __init__(
        self,
        *,
        repeat_probability: float = 0.95,
        reason: RepeatReason | None = None,
        fail: bool = False,
    ) -> None:
        self.repeat_probability = repeat_probability
        self.reason = reason
        self.fail = fail
        self.asked: list[str] = []

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.asked.extend(questions)
        if self.fail:
            raise TypedJudgmentUnavailableException(
                "timeout", error_code="TYPED_JUDGMENT_TIMEOUT"
            )
        answers: dict[str, JudgmentResult] = {}
        for name in questions:
            if name == SEMANTIC_REPEAT_QUESTION:
                answers[name] = JudgmentResult(
                    value=self.repeat_probability, probabilities={}, confidence=None,
                    source=JudgmentSource.STUB, latency_ms=2.0,
                )
            elif name == LOOP_DIAGNOSIS_QUESTION and self.reason is not None:
                answers[name] = JudgmentResult(
                    value=self.reason.value,
                    probabilities={self.reason.value: 0.9},
                    confidence=0.9,
                    source=JudgmentSource.STUB,
                    latency_ms=2.0,
                )
        return answers


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind, *, tick=None, player_id=None, **payload):  # type: ignore[no-untyped-def,override]
        self.calls.append((kind, {"tick": tick, "player_id": player_id, **payload}))
        return super().record(kind, tick=tick, player_id=player_id, **payload)

    def of(self, kind: str, **match: Any) -> list[dict[str, Any]]:
        return [
            p for k, p in self.calls
            if k == kind and all(p.get(f) == v for f, v in match.items())
        ]


def _guard(
    port: _Port,
    *,
    buffer: DefaultObservationContextBuffer,
    recorder: _Recorder | None = None,
    window: int = 3,
    diagnose: bool = False,
) -> ToolCallLoopGuardService:
    return ToolCallLoopGuardService(
        buffer,
        time_label_provider=lambda: "夕方 5:00",
        clock=lambda: datetime(2026, 1, 1),
        trace_recorder=recorder,
        current_tick_provider=lambda: 53,
        loop_diagnosis=LoopDiagnosis(port=port) if diagnose else None,
        location_provider=lambda pid: "祭りの広場",
        semantic_repeat_detector=SemanticRepeatDetector(
            port,
            player_name_resolver=lambda pid: "ガレン",
            window_size=window,
            threshold=0.8,
            trace_recorder_provider=lambda: recorder,
        ),
    )


def _rephrase(guard: ToolCallLoopGuardService, times: int) -> None:
    """ユノへの同じ申し出を、言い回しと宛先の書き方を変えて繰り返す。"""
    variants = (
        {"channel": "say", "content": "ユノ、麦束と薬草を交換しないか", "target_label": "ユノ"},
        {"channel": "say", "content": "ユノ、麦束なら持ってる。薬草と替えよう"},
        {"channel": "say", "content": "なあユノ、薬草と麦束の交換はどうだ"},
    )
    for i in range(times):
        guard.record_and_check(
            _GAREN, "speak", variants[i % len(variants)],
            success=True, result_summary="（2 名に届いた）",
        )


def _warnings(buffer: DefaultObservationContextBuffer) -> list[Any]:
    return [
        e.output
        for e in buffer.get_observations(_GAREN)
        if (e.output.structured or {}).get("loop_guard")
    ]


class TestARephrasedRequestIsWarned:
    """完全一致で数えられない言い直しでも、確率が閾値以上なら警告を 1 件出すことを保証する。"""

    def test_k_rephrased_requests_emit_one_warning(self) -> None:
        """言い直した同じ依頼が K 件並び、確率が閾値以上なら、警告の観測を 1 件出す。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_Port(repeat_probability=0.95), buffer=buffer)

        _rephrase(guard, 3)

        [warning] = _warnings(buffer)
        assert warning.structured["pattern"] == "semantic_repeat"
        assert warning.structured["count"] == 3

    def test_below_the_threshold_nothing_is_emitted(self) -> None:
        """確率が閾値未満なら、警告の観測を出さない。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_Port(repeat_probability=0.79), buffer=buffer)

        _rephrase(guard, 3)

        assert _warnings(buffer) == []

    def test_an_unavailable_judgment_emits_nothing(self) -> None:
        """判断ポートが例外を投げたとき、警告の観測を出さない。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_Port(fail=True), buffer=buffer)

        _rephrase(guard, 3)

        assert _warnings(buffer) == []

    def test_the_default_wording_states_facts_without_ordering(self) -> None:
        """見立てが無いときの文面は、件数と最後の行動を伝え、命令の言い回しを含まない。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_Port(), buffer=buffer)

        _rephrase(guard, 3)

        [warning] = _warnings(buffer)
        assert "3 回" in warning.prose
        assert "`speak`" in warning.prose
        assert not any(d in warning.prose for d in _DIRECTIVES)

    def test_the_warning_is_traced_and_arms_the_reason_first_gate(self) -> None:
        """LOOP_GUARD_WARNING に pattern=semantic_repeat で残し、reason-first 用の gate signal を立てる。"""
        buffer = DefaultObservationContextBuffer()
        recorder = _Recorder()
        guard = _guard(_Port(), buffer=buffer, recorder=recorder)

        _rephrase(guard, 3)

        [event] = recorder.of(TraceEventKind.LOOP_GUARD_WARNING)
        assert event["pattern"] == "semantic_repeat"
        assert event["window_count"] == 3
        signal = guard.consume_gate_signal(_GAREN)
        assert signal is not None
        assert signal.pattern == "semantic_repeat"


class TestAnExactMatchOnTheSameActionIsNotDoubled:
    """同じ行動で完全一致の検出も発火したとき、観測を 1 件にまとめることを保証する。"""

    def test_only_the_exact_match_warning_is_emitted(self) -> None:
        """引数まで同じ wait が 3 回続き両方が発火しても、観測は完全一致の 1 件だけ。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_Port(repeat_probability=0.95), buffer=buffer)

        for _ in range(3):
            guard.record_and_check(_GAREN, "wait", {}, success=True, result_summary="待った")

        [warning] = _warnings(buffer)
        assert warning.structured.get("pattern") != "semantic_repeat"
        assert warning.structured["consecutive_count"] == 3

    def test_the_semantic_judgment_records_that_the_exact_match_fired(self) -> None:
        """まとめて捨てた側の判断も trace に残り、exact_match_fired=True を持つ。"""
        buffer = DefaultObservationContextBuffer()
        recorder = _Recorder()
        guard = _guard(_Port(repeat_probability=0.95), buffer=buffer, recorder=recorder)

        for _ in range(3):
            guard.record_and_check(_GAREN, "wait", {}, success=True, result_summary="待った")

        [judgment] = recorder.of(TraceEventKind.TYPED_JUDGMENT, question=SEMANTIC_REPEAT_QUESTION)
        assert judgment["accepted"] is True
        assert judgment["exact_match_fired"] is True
        assert [
            e["pattern"] if "pattern" in e else "streak"
            for e in recorder.of(TraceEventKind.LOOP_GUARD_WARNING)
        ] == ["streak"]


class TestTheDiagnosisAppliesToSemanticRepeats:
    """意味上の繰り返しの警告も、見立て (#1411) を通って文面を選ぶことを保証する。"""

    def test_a_diagnosed_reason_chooses_the_wording(self) -> None:
        """見立てが「返事待ちの再依頼」なら、その理由の文面になり、判断の trace に pattern が残る。"""
        buffer = DefaultObservationContextBuffer()
        recorder = _Recorder()
        port = _Port(reason=RepeatReason.UNANSWERED_REQUEST)
        guard = _guard(port, buffer=buffer, recorder=recorder, diagnose=True)

        _rephrase(guard, 3)

        [warning] = _warnings(buffer)
        assert "3 回" in warning.prose
        [diagnosis] = recorder.of(TraceEventKind.TYPED_JUDGMENT, question=LOOP_DIAGNOSIS_QUESTION)
        assert diagnosis["pattern"] == "semantic_repeat"
        assert diagnosis["reason"] == RepeatReason.UNANSWERED_REQUEST.value
        [event] = recorder.of(TraceEventKind.LOOP_GUARD_WARNING)
        assert event["wording"] == RepeatReason.UNANSWERED_REQUEST.value


class TestWithoutTheDetector:
    """検出器を渡さないときは、判断ポートを呼ばず、今と同じ振る舞いになることを保証する。"""

    def test_no_detector_means_no_semantic_warning(self) -> None:
        """意味上の検出器を組まなければ、言い直しを何回しても警告は出ない (完全一致の検出だけが動く)。"""
        buffer = DefaultObservationContextBuffer()
        guard = ToolCallLoopGuardService(
            buffer,
            time_label_provider=lambda: "夕方 5:00",
            current_tick_provider=lambda: 53,
        )

        _rephrase(guard, 6)

        assert _warnings(buffer) == []


class _BrokenPort(_Port):
    def judge(self, state, questions):  # type: ignore[no-untyped-def,override]
        self.asked.extend(questions)
        raise RuntimeError("adapter bug")


def _patterns(buffer: DefaultObservationContextBuffer) -> list[str]:
    return [w.structured.get("pattern", "streak") for w in _warnings(buffer)]


class TestTheSameRepetitionIsNotWarnedOnNeighbouringTurns:
    """完全一致の警告と意味上の警告が、同じ繰り返しに隣り合うターンで重ならないことを保証する。"""

    def test_nine_waits_with_the_default_window_are_warned_only_by_the_streak(self) -> None:
        """K=4 で引数まで同じ wait を 9 回続けると、警告は連続の 3・6・9 回目の 3 件だけ。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_Port(repeat_probability=0.95), buffer=buffer, window=4)

        for _ in range(9):
            guard.record_and_check(_GAREN, "wait", {}, success=True, result_summary="待った")

        assert _patterns(buffer) == ["streak", "streak", "streak"]


class TestOneRecordGivesOneWarning:
    """同じ行動で連続と離れた tick の失敗の両方が発火しても、観測を 1 件にまとめることを保証する。"""

    def _fail_travel_twice(self, buffer: DefaultObservationContextBuffer) -> tuple[Any, Any]:
        guard = ToolCallLoopGuardService(
            buffer,
            time_label_provider=lambda: "夕方 5:00",
            current_tick_provider=lambda: 53,
            cross_tick_failure_threshold=2,
        )
        results = [
            guard.record_and_check(
                _GAREN, "travel_to", {"destination_label": "祭壇"},
                success=False, error_code="INVALID_DESTINATION_LABEL",
                result_summary="移動先が見つかりません",
            )
            for _ in range(2)
        ]
        return guard, results[-1]

    def test_only_the_cross_tick_failure_warning_is_emitted(self) -> None:
        """travel_to の同じ失敗が 2 回で両方の閾値に届いても、観測は失敗の理由を持つ 1 件だけ。"""
        buffer = DefaultObservationContextBuffer()

        self._fail_travel_twice(buffer)

        [warning] = _warnings(buffer)
        assert warning.structured["pattern"] == "cross_tick_failure"

    def test_the_cross_tick_trigger_is_still_returned(self) -> None:
        """まとめても、belief への転記に使う CrossTickFailureTrigger は返る。"""
        buffer = DefaultObservationContextBuffer()

        _, trigger = self._fail_travel_twice(buffer)

        assert trigger is not None
        assert trigger.error_code == "INVALID_DESTINATION_LABEL"


class TestAnUnexpectedErrorKeepsTheExactWarning:
    """意味上の判断が想定外の例外を投げても、完全一致の警告は出ることを保証する。"""

    def test_a_broken_port_does_not_swallow_the_streak_warning(self) -> None:
        """判断ポートが RuntimeError を投げても、wait 3 回の連続の警告は出る。"""
        buffer = DefaultObservationContextBuffer()
        guard = _guard(_BrokenPort(), buffer=buffer, window=3)

        for _ in range(3):
            guard.record_and_check(_GAREN, "wait", {}, success=True, result_summary="待った")

        assert _patterns(buffer) == ["streak"]
