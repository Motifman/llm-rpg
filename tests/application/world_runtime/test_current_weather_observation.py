"""旧天候イベントを使わず、現行の天候更新が観測とtraceへ届くことを守る。"""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from tests.support.trace_recorders import CollectingTraceRecorder

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


@pytest.mark.parametrize("is_outdoor", [False, True], ids=["indoor", "outdoor"])
@pytest.mark.parametrize("announce", [False, True], ids=["silent", "announced"])
def test_current_weather_reaches_each_player_when_announced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, is_outdoor: bool, announce: bool
) -> None:
    """天候更新を通知すると屋内外とも全員へ文面・trace・手番予約が届き、通知無効なら届かない。"""
    scenario = json.loads(Path("data/scenarios/survival_island_v2.json").read_text())
    for spot in scenario["spots"]:
        spot["is_outdoor"] = is_outdoor
    scenario["environment"]["weather"]["announce_changes"] = announce
    scenario_path = tmp_path / "weather.json"
    scenario_path.write_text(json.dumps(scenario, ensure_ascii=False))
    runtime = create_world_runtime(scenario_path, config=ResolvedLlmRuntimeConfig.for_tests())
    graph = runtime._spot_graph_repo.find_graph()
    players = runtime.get_player_ids()
    assert players
    for player in players:
        spot_id = graph.get_entity_spot(EntityId(player.value))
        assert graph.get_spot(spot_id).is_outdoor is is_outdoor
        runtime._obs_buffer.drain(player)
    tracer = CollectingTraceRecorder()
    runtime.set_trace_recorder(tracer)
    scheduler = Mock()
    runtime.set_observation_turn_scheduler(scheduler)
    rain = WeatherState(WeatherTypeEnum.RAIN, 0.5)
    monkeypatch.setattr(WeatherSimulationService, "simulate_next_weather", lambda *args, **kwargs: rain)

    runtime._environment_stage.run(WorldTick(25))

    assert runtime._current_weather["state"] == rain
    for player in players:
        outputs = [entry.output for entry in runtime._obs_buffer.drain(player)]
        assert len(outputs) == int(announce)
        if announce:
            assert outputs[0].prose == "外の天候が変わった: RAIN（強度 0.5）"
            assert outputs[0].structured == {"type": "weather_changed", "weather_type": "RAIN", "intensity": 0.5}
            assert outputs[0].observation_category == "environment"
            assert outputs[0].schedules_turn is True
            assert outputs[0].breaks_movement is False
    observations = tracer.of_kind("observation")
    assert [event.player_id for event in observations] == ([player.value for player in players] if announce else [])
    assert all(event.payload["structured"]["type"] == "weather_changed" for event in observations)
    assert scheduler.maybe_schedule.call_count == (len(players) if announce else 0)
