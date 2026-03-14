import pytest
import unittest.mock as mock

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.domain.common.value_object import WorldTick

from .support.world_simulation_builders import build_world_simulation_test_bed


def test_tick_runs_post_tick_hooks_after_hit_box_stage():
    bed = build_world_simulation_test_bed()
    service = bed.service
    order: list[str] = []

    service._environment_stage = mock.Mock(
        run=mock.Mock(side_effect=lambda current_tick, maps: order.append("environment"))
    )
    service._monster_lifecycle_stage = mock.Mock(
        run=mock.Mock(side_effect=lambda maps, active_spot_ids, current_tick: order.append("lifecycle") or set())
    )
    service._monster_behavior_stage = mock.Mock(
        run=mock.Mock(
            side_effect=lambda maps, active_spot_ids, current_tick, skipped_actor_ids=None: order.append(
                "behavior"
            )
        )
    )
    service._hit_box_stage = mock.Mock(
        run=mock.Mock(side_effect=lambda maps, active_spot_ids, current_tick: order.append("hitbox"))
    )
    service._llm_turn_trigger = mock.Mock(
        run_scheduled_turns=mock.Mock(side_effect=lambda: order.append("llm"))
    )
    service._reflection_runner = mock.Mock(
        run_after_tick=mock.Mock(side_effect=lambda current_tick: order.append("reflection"))
    )

    current_tick = service.tick()

    assert current_tick == WorldTick(11)
    assert order[-3:] == ["hitbox", "llm", "reflection"]


def test_tick_runs_reflection_runner_with_current_tick():
    bed = build_world_simulation_test_bed()
    service = bed.service
    reflection_runner = mock.Mock()
    service._reflection_runner = reflection_runner

    current_tick = service.tick()

    reflection_runner.run_after_tick.assert_called_once_with(current_tick)


def test_tick_wraps_reflection_runner_failures_as_system_error():
    bed = build_world_simulation_test_bed()
    service = bed.service
    reflection_runner = mock.Mock()
    reflection_runner.run_after_tick.side_effect = RuntimeError("reflection failed")
    service._reflection_runner = reflection_runner

    with pytest.raises(SystemErrorException, match="tick failed") as exc_info:
        service.tick()

    assert isinstance(exc_info.value.original_exception, RuntimeError)
    assert "reflection failed" in str(exc_info.value.original_exception)
