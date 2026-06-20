"""create_world_runtime が SpotGraphSimulationApplicationService に ILlmTurnTrigger を渡すこと。"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "abandoned_hospital.json"


def test_create_world_runtime_installs_noop_llm_turn_trigger() -> None:
    from ai_rpg_world.application.world_runtime.world_runtime import (
        WorldStandaloneNoopLlmTurnTrigger,
        create_world_runtime,
    )

    runtime = create_world_runtime(SCENARIO_PATH)
    tr = runtime._simulation_service._llm_turn_trigger
    assert tr is not None
    assert isinstance(tr, WorldStandaloneNoopLlmTurnTrigger)


def test_set_simulation_llm_turn_trigger_replaces_post_tick_hook() -> None:
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    class _RecordingTrigger:
        def __init__(self) -> None:
            self.runs = 0

        def schedule_turn(self, player_id: PlayerId) -> None:  # noqa: ARG002
            return None

        def run_scheduled_turns(self) -> None:
            self.runs += 1

    runtime = create_world_runtime(SCENARIO_PATH)
    rec = _RecordingTrigger()
    runtime.set_simulation_llm_turn_trigger(rec)
    assert runtime._simulation_service._llm_turn_trigger is rec
    runtime.advance_tick()
    assert rec.runs == 1
