"""tick の終わりに「いま動く必要があるか」を問う門の仕様。

判断の対象は social の観測だけが溜まった人。本人や世界の変化 (self_only /
environment)、囁き、名指し、沈黙の上限、未読なしは判断を引かずに回す。会議中は
候補の中で少なくとも 1 人を回す。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
from ai_rpg_world.application.llm.services.world_llm_turn.turn_gate import (
    QUESTION_NAME,
    REASON_JUDGED_NEEDED,
    REASON_JUDGED_UNNEEDED,
    REASON_JUDGMENT_UNAVAILABLE,
    REASON_MEETING_FLOOR,
    REASON_NAMED_IN_SPEECH,
    REASON_NO_PENDING,
    REASON_NOT_ONLY_SOCIAL,
    REASON_SILENCE_LIMIT,
    REASON_WHISPERED_TO_ME,
    TurnGate,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

MORI, SENA, KUZE = PlayerId(1), PlayerId(2), PlayerId(3)
NAMES = {1: "モリ", 2: "セナ", 3: "クゼ"}


class _Port(ITypedJudgmentPort):
    """名前ごとの確率を返し、渡された state を記録する。"""

    def __init__(self, by_name: Mapping[str, float] | None = None, default: float = 0.5) -> None:
        self.by_name = dict(by_name or {})
        self.default = default
        self.calls: list[tuple[Any, Mapping[str, Any]]] = []

    def judge(self, state, questions):
        self.calls.append((state, dict(questions)))
        name = state["listener"]["name"]
        return {
            q: JudgmentResult(
                value=self.by_name.get(name, self.default),
                probabilities={}, confidence=None,
                source=JudgmentSource.JEV, latency_ms=8.0,
            )
            for q in questions
        }


class _FailingPort(ITypedJudgmentPort):
    def judge(self, state, questions):
        raise TypedJudgmentUnavailableException("down", error_code="TYPED_JUDGMENT_TRANSPORT_FAILED")


class _Recorder:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, kind, **payload) -> None:
        assert kind is TraceEventKind.TYPED_JUDGMENT
        self.events.append(payload)


def _speech(speaker: str = "クゼ", content: str = "サキが倒れてた。", channel: str = "say") -> ObservationOutput:
    return ObservationOutput(
        prose=f"{speaker}が言った: 「{content}」",
        structured={"type": "player_spoke", "speaker": speaker, "channel": channel, "content": content},
        observation_category="social", schedules_turn=True,
    )


def _alarm() -> ObservationOutput:
    return ObservationOutput(
        prose="警報が鳴った。", structured={"type": "scenario_event"},
        observation_category="environment", schedules_turn=True,
    )


class _World:
    """門に渡す世界の断片。tick、会議中か、各人の未読観測。"""

    def __init__(self) -> None:
        self.tick = 10
        self.meeting = False
        self.pending: dict[int, list[ObservationOutput]] = {}
        self.recorder = _Recorder()

    def gate(self, port: ITypedJudgmentPort, **kwargs: Any) -> TurnGate:
        return TurnGate(
            port,
            current_tick_provider=lambda: self.tick,
            player_name_resolver=lambda pid: NAMES[int(pid.value)],
            pending_observations_provider=lambda pid: self.pending.get(int(pid.value), []),
            is_meeting_provider=lambda: self.meeting,
            trace_recorder_provider=lambda: self.recorder,
            **kwargs,
        )


class TestTheGateWakesBeforeJudging:
    """判断を引かずに回す条件。"""

    def test_a_player_with_no_pending_observation_runs(self) -> None:
        """未読の観測が無い人 (自己 reschedule で pending に居る人) は判断を引かず回す。"""
        w = _World(); port = _Port()

        assert w.gate(port).decide_wave([MORI]) == [MORI]
        assert port.calls == []
        assert w.recorder.events[0]["reason"] == REASON_NO_PENDING

    def test_a_self_or_world_observation_runs_without_asking(self) -> None:
        """self_only / environment の観測が 1 件でもあれば、判断を引かず回す。"""
        w = _World(); port = _Port()
        w.pending[1] = [_speech(), _alarm()]

        assert w.gate(port).decide_wave([MORI]) == [MORI]
        assert port.calls == []
        assert w.recorder.events[0]["reason"] == REASON_NOT_ONLY_SOCIAL

    def test_a_whisper_runs_without_asking(self) -> None:
        """囁きが届いていれば、判断を引かず回す。"""
        w = _World(); port = _Port({"モリ": 0.0})
        w.pending[1] = [_speech(channel="whisper")]

        assert w.gate(port).decide_wave([MORI]) == [MORI]
        assert w.recorder.events[0]["reason"] == REASON_WHISPERED_TO_ME

    def test_being_named_runs_without_asking(self) -> None:
        """本文に自分の名前がある発言が届いていれば、判断を引かず回す。"""
        w = _World(); port = _Port({"モリ": 0.0})
        w.pending[1] = [_speech(content="モリ、配電盤はどうなった？")]

        assert w.gate(port).decide_wave([MORI]) == [MORI]
        assert w.recorder.events[0]["reason"] == REASON_NAMED_IN_SPEECH

    def test_a_player_silent_for_the_limit_runs_without_asking(self) -> None:
        """silence_limit_ticks の間回っていない人は、判断を引かず回す。"""
        w = _World(); port = _Port({"モリ": 0.0})
        w.pending[1] = [_speech()]
        gate = w.gate(port, silence_limit_ticks=3)
        assert gate.decide_wave([MORI]) == []
        w.tick = 12
        assert gate.decide_wave([MORI]) == []

        w.tick = 13
        assert gate.decide_wave([MORI]) == [MORI]
        assert w.recorder.events[-1]["reason"] == REASON_SILENCE_LIMIT


class TestTheJudgmentDecidesSocialOnlyTicks:
    """social の観測だけが溜まった人は、確率が閾値未満のときだけ回さない。"""

    def test_a_low_probability_keeps_the_player_asleep(self) -> None:
        """閾値未満なら回さず、trace に確率・閾値・採否・latency・source が残る。"""
        w = _World(); port = _Port({"モリ": 0.05})
        w.pending[1] = [_speech(), _speech(speaker="セナ", content="温室へ行く。")]

        assert w.gate(port, skip_below=0.15).decide_wave([MORI]) == []
        e = w.recorder.events[0]
        assert e["question"] == QUESTION_NAME and e["player_id"] == 1
        assert e["woke"] is False and e["reason"] == REASON_JUDGED_UNNEEDED
        assert e["probability"] == 0.05 and e["skip_below"] == 0.15
        assert e["pending_count"] == 2 and e["latency_ms"] == 8.0 and e["source"] == "jev"

    def test_a_probability_at_the_threshold_runs(self) -> None:
        """閾値と等しければ回す。落とすのは厳密に未満のときだけ。"""
        w = _World(); port = _Port({"モリ": 0.15})
        w.pending[1] = [_speech()]

        assert w.gate(port, skip_below=0.15).decide_wave([MORI]) == [MORI]
        assert w.recorder.events[0]["reason"] == REASON_JUDGED_NEEDED

    def test_the_stub_never_suppresses(self) -> None:
        """決定論 stub (0.5) では誰も止まらず、現行の振る舞いのまま通る。"""
        w = _World(); w.pending[1] = [_speech()]

        assert w.gate(DeterministicTypedJudgmentPort()).decide_wave([MORI]) == [MORI]

    def test_an_unavailable_judgment_runs_and_keeps_the_reason(self) -> None:
        """ポートが失敗したら回し、unavailable_reason を残す。"""
        w = _World(); w.pending[1] = [_speech()]

        assert w.gate(_FailingPort()).decide_wave([MORI]) == [MORI]
        e = w.recorder.events[0]
        assert e["reason"] == REASON_JUDGMENT_UNAVAILABLE
        assert e["unavailable_reason"] == "TYPED_JUDGMENT_TRANSPORT_FAILED"

    def test_one_judgment_per_player_covers_every_pending_speech(self) -> None:
        """発言が何件届いていても、1 人につき判断は 1 回で、state に全件の本文が入る。"""
        w = _World(); port = _Port()
        w.pending[1] = [_speech(content=f"発言 {i}") for i in range(7)]

        w.gate(port).decide_wave([MORI])

        assert len(port.calls) == 1
        state, questions = port.calls[0]
        assert len(state["observations_this_tick"]) == 7
        assert state["listener"] == {"name": "モリ", "in_meeting": False}
        assert isinstance(questions[QUESTION_NAME], NoulQuestion)
        assert "1" not in repr(state["listener"])


class TestTheMeetingKeepsOneAwake:
    """会議中に全員が止まると会議が流れるので、少なくとも 1 人は回す。"""

    def test_when_everyone_would_sleep_in_a_meeting_the_most_likely_runs(self) -> None:
        """会議中に候補全員が閾値未満なら、確率が最も高い 1 人だけを meeting_floor で回す。"""
        w = _World(); w.meeting = True
        port = _Port({"モリ": 0.05, "セナ": 0.10, "クゼ": 0.07})
        for k in (1, 2, 3): w.pending[k] = [_speech(speaker="ユラ")]

        assert w.gate(port).decide_wave([MORI, SENA, KUZE]) == [SENA]
        by = {e["player_id"]: e for e in w.recorder.events}
        assert by[2]["reason"] == REASON_MEETING_FLOOR and by[2]["woke"] is True
        assert by[1]["reason"] == REASON_JUDGED_UNNEEDED and by[1]["woke"] is False

    def test_outside_a_meeting_everyone_may_sleep(self) -> None:
        """会議中でなければ、全員が閾値未満なら全員止まる (**正の対照**)。"""
        w = _World(); port = _Port(default=0.05)
        for k in (1, 2): w.pending[k] = [_speech(speaker="ユラ")]

        assert w.gate(port).decide_wave([MORI, SENA]) == []

    def test_a_meeting_with_someone_already_awake_adds_nobody(self) -> None:
        """会議中でも誰か 1 人が回るなら、他の人を足さない。"""
        w = _World(); w.meeting = True
        port = _Port({"モリ": 0.05, "セナ": 0.9})
        for k in (1, 2): w.pending[k] = [_speech(speaker="ユラ")]

        assert w.gate(port).decide_wave([MORI, SENA]) == [SENA]


class TestConstruction:
    def test_a_threshold_outside_the_unit_interval_is_rejected(self) -> None:
        """skip_below が (0, 1] の外なら ValueError になる。"""
        with pytest.raises(ValueError):
            _World().gate(_Port(), skip_below=0.0)

    def test_a_silence_limit_below_one_is_rejected(self) -> None:
        """silence_limit_ticks が 1 未満なら ValueError になる。"""
        with pytest.raises(ValueError):
            _World().gate(_Port(), silence_limit_ticks=0)
