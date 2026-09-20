"""本番の入口から組んだ世界で、発言 1 件が門を通って聞き手の起床を決める。

門のクラス・scheduler の差し込み口・配線の 3 つが揃っていても、発言が
pipeline を通って scheduler に届かなければ run では何も変わらない。
実際の発言 (``do_say``) を起こし、届いた trace と起床の有無を見る。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.observation.services.speech_reply_gate import (
    QUESTION_NAME,
    REASON_JUDGED_NEEDED,
    REASON_JUDGED_UNNEEDED,
    REASON_NAMED_IN_SPEECH,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"
)


class _Recorder:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, kind, **payload) -> None:
        if kind is TraceEventKind.TYPED_JUDGMENT:
            self.events.append(payload)


@pytest.fixture
def world() -> Iterator[Any]:
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        GameRuntimeManager,
    )
    from ai_rpg_world.presentation.spot_graph_game.schemas import (
        CharacterCreateRequest,
        SessionCreateRequest,
    )

    with TemporaryDirectory() as tmp:
        manager = GameRuntimeManager(
            scenarios_dir=_SCENARIO.parent,
            characters_path=Path(tmp) / "characters.json",
            runtime_config=ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="stub"
            ),
        )
        character = manager.create_character(CharacterCreateRequest(name="probe"))
        summary = manager.create_session(
            SessionCreateRequest(world_id=_SCENARIO.stem, character_ids=[character.id])
        )
        yield manager._sessions[summary.session_id].llm_wiring


def _ids_by_name(runtime: Any) -> dict[str, PlayerId]:
    return {
        spawn.name: PlayerId(int(spawn.player_id))
        for spawn in runtime.scenario.player_spawns
    }


class TestASpeechPassesThroughTheGate:
    """do_say で起きた発言が、聞き手ごとに門を通り、trace と起床に反映される。"""

    def test_with_the_stub_every_listener_is_judged_and_woken(self, world: Any) -> None:
        """stub (0.5) では聞き手全員が判断を経て起こされ、聞き手ごとに trace が 1 件残る。"""
        runtime = world.runtime
        recorder = _Recorder()
        runtime.set_trace_recorder(recorder)
        ids = _ids_by_name(runtime)
        trigger = world.llm_turn_trigger
        trigger.pending_player_ids.clear()

        runtime.do_say(ids["モリ"], "配電盤を確認してくる。")

        listeners = {name for name in ids if name != "モリ"}
        assert {event["listener"] for event in recorder.events} == listeners
        assert all(event["question"] == QUESTION_NAME for event in recorder.events)
        assert all(event["woke"] is True for event in recorder.events)
        assert all(event["reason"] == REASON_JUDGED_NEEDED for event in recorder.events)
        assert all(event["speaker"] == "モリ" for event in recorder.events)
        assert trigger.pending_player_ids == {ids[name].value for name in listeners}

    def test_a_low_probability_keeps_listeners_asleep_but_keeps_the_observation(
        self, world: Any
    ) -> None:
        """返答不要と判断された聞き手は起きないが、発言の観測は buffer に残る。名指しされた人は起きる。"""
        runtime = world.runtime
        recorder = _Recorder()
        runtime.set_trace_recorder(recorder)
        ids = _ids_by_name(runtime)
        gate = runtime._observation_turn_scheduler.wake_gate
        gate.judgment_port = DeterministicTypedJudgmentPort(answers={QUESTION_NAME: 0.0})
        trigger = world.llm_turn_trigger
        trigger.pending_player_ids.clear()

        runtime.do_say(ids["モリ"], "セナ、配電盤はどうなった？")

        assert trigger.pending_player_ids == {ids["セナ"].value}
        by_listener = {event["listener"]: event for event in recorder.events}
        assert by_listener["セナ"]["reason"] == REASON_NAMED_IN_SPEECH
        assert by_listener["クゼ"]["reason"] == REASON_JUDGED_UNNEEDED
        assert by_listener["クゼ"]["woke"] is False
        assert by_listener["クゼ"]["probability"] == 0.0
        heard = [
            entry.output.prose
            for entry in runtime._obs_buffer.get_observations(ids["クゼ"])
        ]
        assert any("セナ、配電盤はどうなった？" in text for text in heard)
