"""他者の発言で起こすかを、返答の必要性で決める門の仕様。

門で守るもの (囁き / 名指し / 沈黙の上限) は判断を引かずに起こす。判断は
明らかに返答不要なときだけ起こさない側に働く。判断が得られなければ起こす。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.speech_reply_gate import (
    QUESTION_NAME,
    REASON_JUDGED_NEEDED,
    REASON_JUDGED_UNNEEDED,
    REASON_JUDGMENT_UNAVAILABLE,
    REASON_NAMED_IN_SPEECH,
    REASON_NOT_SPEECH,
    REASON_SILENCE_LIMIT,
    REASON_WHISPERED_TO_ME,
    SpeechReplyGate,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

MORI = PlayerId(1)
SENA = PlayerId(2)
NAMES = {1: "モリ", 2: "セナ", 3: "クゼ"}


class _RecordingPort(ITypedJudgmentPort):
    """渡された state と質問を記録し、固定の確率を返す。"""

    def __init__(self, probability: float) -> None:
        self.probability = probability
        self.calls: list[tuple[Any, Mapping[str, Any]]] = []

    def judge(self, state, questions):
        self.calls.append((state, dict(questions)))
        return {
            name: JudgmentResult(
                value=self.probability,
                probabilities={},
                confidence=None,
                source=JudgmentSource.JEV,
                latency_ms=12.5,
            )
            for name in questions
        }


class _FailingPort(ITypedJudgmentPort):
    def judge(self, state, questions):
        raise TypedJudgmentUnavailableException(
            "timeout", error_code="TYPED_JUDGMENT_TRANSPORT_FAILED"
        )


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[Any, dict]] = []

    def record(self, kind, **payload) -> None:
        self.events.append((kind, payload))


def _speech(
    speaker: str = "クゼ",
    speaker_id: int = 3,
    content: str = "サキが倒れてるのを見つけたんだ。",
    channel: str = "say",
) -> ObservationOutput:
    return ObservationOutput(
        prose=f"{speaker}が言った: 「{content}」",
        structured={
            "type": "player_spoke",
            "speaker": speaker,
            "speaker_player_id": speaker_id,
            "channel": channel,
            "content": content,
            "role": "other",
        },
        observation_category="social",
        schedules_turn=True,
    )


class _Clock:
    def __init__(self, tick: int = 10) -> None:
        self.tick = tick

    def __call__(self) -> int:
        return self.tick


def _gate(
    port: ITypedJudgmentPort,
    *,
    clock: Optional[_Clock] = None,
    recorder: Optional[_Recorder] = None,
    recent: Optional[list[str]] = None,
    **kwargs: Any,
) -> SpeechReplyGate:
    return SpeechReplyGate(
        port,
        current_tick_provider=clock or _Clock(),
        listener_name_resolver=lambda pid: NAMES[int(pid.value)],
        recent_observations_provider=(lambda pid: list(recent)) if recent else None,
        trace_recorder_provider=(lambda: recorder) if recorder else None,
        **kwargs,
    )


class TestTheGateOnlyJudgesSpeech:
    """player_spoke 以外の観測は門の対象外で、判断を引かずに起こす。"""

    def test_a_non_speech_observation_wakes_without_asking(self) -> None:
        """発言でない観測 (投票の要求など) は判断を引かず、wake=True になる。"""
        port = _RecordingPort(0.0)
        output = ObservationOutput(
            prose="投票を求められた。",
            structured={"type": "meeting_vote_requested"},
            schedules_turn=True,
        )

        decision = _gate(port).decide(MORI, output)

        assert decision.wake is True
        assert decision.reason == REASON_NOT_SPEECH
        assert port.calls == []


class TestTheGateWakesBeforeJudging:
    """自分宛てと沈黙の上限は、判断に委ねずに起こす。"""

    def test_a_whisper_wakes_without_asking(self) -> None:
        """囁きは宛先本人にしか届かないので、判断を引かず起こす。"""
        port = _RecordingPort(0.0)

        decision = _gate(port).decide(MORI, _speech(channel="whisper"))

        assert decision.wake is True
        assert decision.reason == REASON_WHISPERED_TO_ME
        assert port.calls == []

    def test_a_speech_naming_the_listener_wakes_without_asking(self) -> None:
        """本文に聞き手の名前があれば、判断を引かず起こす。"""
        port = _RecordingPort(0.0)

        decision = _gate(port).decide(
            MORI, _speech(content="モリ、配電盤はどうなった？")
        )

        assert decision.wake is True
        assert decision.reason == REASON_NAMED_IN_SPEECH
        assert port.calls == []

    def test_a_speech_naming_someone_else_is_judged(self) -> None:
        """他人の名前だけが出た発言は、名指しとして扱わず判断へ進む (**正の対照**)。"""
        port = _RecordingPort(0.0)

        decision = _gate(port).decide(
            MORI, _speech(content="セナ、配電盤はどうなった？")
        )

        assert decision.reason == REASON_JUDGED_UNNEEDED
        assert len(port.calls) == 1

    def test_a_listener_silent_for_the_limit_wakes_without_asking(self) -> None:
        """初めて門を通った tick から silence_limit_ticks 経つと、判断を引かず起こす。"""
        port = _RecordingPort(0.0)
        clock = _Clock(tick=10)
        gate = _gate(port, clock=clock, silence_limit_ticks=3)
        assert gate.decide(MORI, _speech()).reason == REASON_JUDGED_UNNEEDED
        clock.tick = 12
        assert gate.decide(MORI, _speech()).reason == REASON_JUDGED_UNNEEDED

        clock.tick = 13
        decision = gate.decide(MORI, _speech())

        assert decision.wake is True
        assert decision.reason == REASON_SILENCE_LIMIT
        assert len(port.calls) == 2

    def test_speaking_resets_the_listeners_silence(self) -> None:
        """聞き手自身の発言が他の誰かに届くと、その tick から沈黙を数え直す。"""
        port = _RecordingPort(0.0)
        clock = _Clock(tick=10)
        gate = _gate(port, clock=clock, silence_limit_ticks=3)
        gate.decide(MORI, _speech())
        clock.tick = 12
        gate.decide(SENA, _speech(speaker="モリ", speaker_id=1))
        clock.tick = 14

        decision = gate.decide(MORI, _speech())

        assert decision.reason == REASON_JUDGED_UNNEEDED


class TestTheJudgmentDecidesTheRest:
    """門を通った発言は、返答が要る確率が閾値未満のときだけ起こさない。"""

    def test_a_probability_below_the_threshold_does_not_wake(self) -> None:
        """noul が skip_below 未満なら wake=False で、確率と出所が決定に載る。"""
        port = _RecordingPort(0.02)

        decision = _gate(port, skip_below=0.05).decide(MORI, _speech())

        assert decision.wake is False
        assert decision.reason == REASON_JUDGED_UNNEEDED
        assert decision.probability == 0.02
        assert decision.source == "jev"
        assert decision.latency_ms == 12.5

    def test_a_probability_at_the_threshold_wakes(self) -> None:
        """noul が skip_below と等しければ起こす。落とすのは厳密に未満のときだけ。"""
        port = _RecordingPort(0.05)

        decision = _gate(port, skip_below=0.05).decide(MORI, _speech())

        assert decision.wake is True
        assert decision.reason == REASON_JUDGED_NEEDED

    def test_the_stub_never_suppresses(self) -> None:
        """決定論 stub (0.5) では門が誰も抑制せず、現行の振る舞いのまま通る。"""
        decision = _gate(DeterministicTypedJudgmentPort()).decide(MORI, _speech())

        assert decision.wake is True

    def test_an_unavailable_judgment_wakes_and_keeps_the_reason(self) -> None:
        """ポートが失敗したら起こし、unavailable_reason に error_code を残す。"""
        decision = _gate(_FailingPort()).decide(MORI, _speech())

        assert decision.wake is True
        assert decision.reason == REASON_JUDGMENT_UNAVAILABLE
        assert decision.unavailable_reason == "TYPED_JUDGMENT_TRANSPORT_FAILED"


class TestWhatTheJudgmentSees:
    """state には名前だけを入れ、発言の本文と聞き手の直近の状況を渡す。"""

    def test_the_state_carries_names_speech_and_recent_situation(self) -> None:
        """state に話者名・聞こえた本文・聞き手名・直近の観測が入り、整数 ID は入らない。"""
        port = _RecordingPort(0.5)
        recent = ["照明が落ちた。", "クゼが言った: 「サキが倒れてるのを見つけたんだ。」"]

        _gate(port, recent=recent).decide(MORI, _speech())

        state, questions = port.calls[0]
        assert state["speech"]["speaker"] == "クゼ"
        assert state["speech"]["heard"] == "クゼが言った: 「サキが倒れてるのを見つけたんだ。」"
        assert state["listener"]["name"] == "モリ"
        assert state["listener"]["recent_situation"] == ["照明が落ちた。"]
        assert "speaker_player_id" not in repr(state)
        assert "3" not in repr(state)
        question = questions[QUESTION_NAME]
        assert isinstance(question, NoulQuestion)
        assert "モリ" in question.instructions


class TestTheTraceKeepsEveryDecision:
    """採った判断も採らなかった判断も、門で決めた分も TYPED_JUDGMENT に残る。"""

    def test_a_judged_decision_is_traced_with_probability_and_threshold(self) -> None:
        """判断を引いた決定は、確率・閾値・採否・latency・source が 1 件に残る。"""
        recorder = _Recorder()

        _gate(_RecordingPort(0.02), recorder=recorder, skip_below=0.05).decide(
            MORI, _speech()
        )

        assert len(recorder.events) == 1
        kind, payload = recorder.events[0]
        assert kind is TraceEventKind.TYPED_JUDGMENT
        assert payload["question"] == QUESTION_NAME
        assert payload["player_id"] == 1
        assert payload["listener"] == "モリ"
        assert payload["speaker"] == "クゼ"
        assert payload["probability"] == 0.02
        assert payload["skip_below"] == 0.05
        assert payload["woke"] is False
        assert payload["reason"] == REASON_JUDGED_UNNEEDED
        assert payload["latency_ms"] == 12.5
        assert payload["source"] == "jev"
        assert payload["unavailable_reason"] is None

    def test_a_gate_decision_is_traced_without_a_probability(self) -> None:
        """門で起こした決定も残り、probability と source は None で理由だけが入る。"""
        recorder = _Recorder()

        _gate(_RecordingPort(0.0), recorder=recorder).decide(
            MORI, _speech(channel="whisper")
        )

        _, payload = recorder.events[0]
        assert payload["woke"] is True
        assert payload["reason"] == REASON_WHISPERED_TO_ME
        assert payload["probability"] is None
        assert payload["source"] is None

    def test_an_unavailable_judgment_is_traced_as_a_fallback(self) -> None:
        """ポート失敗は unavailable_reason 付きで残り、OFF の run と見分けられる。"""
        recorder = _Recorder()

        _gate(_FailingPort(), recorder=recorder).decide(MORI, _speech())

        _, payload = recorder.events[0]
        assert payload["woke"] is True
        assert payload["unavailable_reason"] == "TYPED_JUDGMENT_TRANSPORT_FAILED"

    def test_a_non_speech_observation_leaves_no_trace(self) -> None:
        """発言でない観測は門の対象外なので、trace に何も残さない。"""
        recorder = _Recorder()
        output = ObservationOutput(
            prose="x", structured={"type": "heartbeat"}, schedules_turn=True
        )

        _gate(_RecordingPort(0.0), recorder=recorder).decide(MORI, output)

        assert recorder.events == []


class TestConstruction:
    """閾値と沈黙の上限は範囲外を起動前に拒否する。"""

    def test_a_threshold_outside_the_unit_interval_is_rejected(self) -> None:
        """skip_below が (0, 1] の外なら ValueError になる。"""
        with pytest.raises(ValueError):
            _gate(_RecordingPort(0.5), skip_below=0.0)

    def test_a_silence_limit_below_one_is_rejected(self) -> None:
        """silence_limit_ticks が 1 未満なら ValueError になる。"""
        with pytest.raises(ValueError):
            _gate(_RecordingPort(0.5), silence_limit_ticks=0)
