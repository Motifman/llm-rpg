"""tick の終わりに「いま動く必要があるか」を pending の全員に問う門の仕様。

普通は pending の全員が毎 tick 起動する。門は Jev が「本当に不要」と判定できた人
だけ回さない。規則で判断を飛ばさない。唯一の例外は未読の観測が無い人で、判断の
材料が無いのでそのまま回す。
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
    REASON_NO_PENDING,
    TurnGate,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

MORI, SENA = PlayerId(1), PlayerId(2)
NAMES = {1: "モリ", 2: "セナ"}


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


class TestEveryoneWithSomethingToReadIsJudged:
    """未読の観測がある人は、種類を問わず Jev に問う。規則で素通しさせない。"""

    def test_a_player_with_no_pending_observation_runs_without_asking(self) -> None:
        """未読の観測が無い人 (自己 reschedule で pending に居る人) は材料が無いので、問わずに回す。"""
        w = _World(); port = _Port()

        assert w.gate(port).decide_wave([MORI]) == [MORI]
        assert port.calls == []
        assert w.recorder.events[0]["reason"] == REASON_NO_PENDING

    def test_an_alarm_is_judged_not_waved_through(self) -> None:
        """警報 (environment) が届いた人も Jev に問う。判定が閾値未満なら回さない。"""
        w = _World(); port = _Port({"モリ": 0.05})
        w.pending[1] = [_alarm()]

        assert w.gate(port).decide_wave([MORI]) == []
        assert len(port.calls) == 1
        assert w.recorder.events[0]["reason"] == REASON_JUDGED_UNNEEDED

    def test_being_named_is_judged_not_waved_through(self) -> None:
        """名指しされた人も Jev に問う。名指しは規則ではなく state の材料。"""
        w = _World(); port = _Port({"モリ": 0.05})
        w.pending[1] = [_speech(content="モリ、配電盤はどうなった？")]

        assert w.gate(port).decide_wave([MORI]) == []
        state, _ = port.calls[0]
        assert "モリ、配電盤はどうなった？" in state["observations_this_tick"][0]["text"]

    def test_a_whisper_is_judged_not_waved_through(self) -> None:
        """囁きが届いた人も Jev に問う。"""
        w = _World(); port = _Port({"モリ": 0.05})
        w.pending[1] = [_speech(channel="whisper")]

        assert w.gate(port).decide_wave([MORI]) == []
        assert len(port.calls) == 1

    def test_everyone_may_sleep_even_in_a_meeting(self) -> None:
        """会議中でも、全員が閾値未満なら全員回さない。会議の 1 人保証は置かない。"""
        w = _World(); w.meeting = True; port = _Port(default=0.05)
        for k in (1, 2): w.pending[k] = [_speech(speaker="ユラ")]

        assert w.gate(port).decide_wave([MORI, SENA]) == []


class TestTheJudgmentAndItsTrace:
    def test_a_probability_at_or_above_the_threshold_runs(self) -> None:
        """閾値以上なら回す。閾値と等しい値も回す。"""
        w = _World(); port = _Port({"モリ": 0.15})
        w.pending[1] = [_speech()]

        assert w.gate(port, skip_below=0.15).decide_wave([MORI]) == [MORI]
        assert w.recorder.events[0]["reason"] == REASON_JUDGED_NEEDED

    def test_the_trace_carries_probability_threshold_and_categories(self) -> None:
        """trace に確率・閾値・採否・未読件数・分類の内訳・latency・source が残る。"""
        w = _World(); port = _Port({"モリ": 0.05})
        w.pending[1] = [_speech(), _speech(speaker="セナ"), _alarm()]

        w.gate(port, skip_below=0.15).decide_wave([MORI])

        e = w.recorder.events[0]
        assert e["question"] == QUESTION_NAME and e["player_id"] == 1
        assert e["woke"] is False and e["probability"] == 0.05 and e["skip_below"] == 0.15
        assert e["pending_count"] == 3 and e["categories"] == {"social": 2, "environment": 1}
        assert e["latency_ms"] == 8.0 and e["source"] == "jev"

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

    def test_one_judgment_per_player_carries_every_pending_observation_with_its_kind(self) -> None:
        """発言が何件届いても 1 人につき判断は 1 回で、state に全件の本文と種類が入る。整数 ID は入らない。"""
        w = _World(); port = _Port()
        w.pending[1] = [_speech(content=f"発言 {i}") for i in range(7)] + [_alarm()]

        w.gate(port).decide_wave([MORI])

        assert len(port.calls) == 1
        state, questions = port.calls[0]
        assert len(state["observations_this_tick"]) == 8
        assert state["observations_this_tick"][-1] == {"kind": "世界の変化", "text": "警報が鳴った。"}
        assert state["observations_this_tick"][0]["kind"] == "他者の言動"
        assert state["listener"] == {"name": "モリ", "in_meeting": False}
        assert isinstance(questions[QUESTION_NAME], NoulQuestion)


class TestConstruction:
    def test_a_threshold_outside_the_unit_interval_is_rejected(self) -> None:
        """skip_below が (0, 1] の外なら ValueError になる。"""
        with pytest.raises(ValueError):
            _World().gate(_Port(), skip_below=0.0)


class TestCandidatesIncludeEveryoneWithUnreadObservations:
    """候補は pending の人に加えて、未読の観測が溜まっている人全員。"""

    def _gate(self, w: _World, port: ITypedJudgmentPort) -> TurnGate:
        return TurnGate(
            port,
            current_tick_provider=lambda: w.tick,
            player_name_resolver=lambda pid: NAMES[int(pid.value)],
            pending_observations_provider=lambda pid: w.pending.get(int(pid.value), []),
            is_meeting_provider=lambda: w.meeting,
            all_player_ids_provider=lambda: [SENA, MORI],
            trace_recorder_provider=lambda: w.recorder,
        )

    def test_a_player_with_unread_observations_is_a_candidate_without_being_scheduled(self) -> None:
        """pending に居なくても未読があれば候補に入る。順序は pending の人が先で、残りは ID 順。"""
        w = _World(); w.pending[2] = [_speech()]

        assert self._gate(w, _Port()).candidates([MORI]) == [MORI, SENA]

    def test_a_player_with_nothing_unread_is_not_added(self) -> None:
        """未読が無い人は、pending に居なければ候補に入らない (**正の対照**)。"""
        w = _World()

        assert self._gate(w, _Port()).candidates([MORI]) == [MORI]

    def test_a_sleeper_is_judged_again_next_tick_on_the_same_unread(self) -> None:
        """前の tick に寝た人は、新しい観測が無くても溜まった未読で次の tick に判断し直される。"""
        w = _World(); w.pending[1] = [_speech()]
        port = _Port({"モリ": 0.05}); gate = self._gate(w, port)
        assert gate.decide_wave(gate.candidates([MORI]), scheduled=[MORI]) == []
        w.tick += 1
        port.by_name["モリ"] = 0.5

        woke = gate.decide_wave(gate.candidates([]), scheduled=[])

        assert woke == [MORI]
        assert len(port.calls) == 2
        assert w.recorder.events[-1]["scheduled"] is False

    def test_without_the_provider_only_scheduled_players_are_candidates(self) -> None:
        """all_player_ids_provider が無い構成では、候補は pending の人だけ。"""
        w = _World(); w.pending[2] = [_speech()]

        assert w.gate(_Port()).candidates([MORI]) == [MORI]
