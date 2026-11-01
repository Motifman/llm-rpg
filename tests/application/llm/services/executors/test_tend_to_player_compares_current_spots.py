"""介抱 (tend_to_player) の同席の判定が、出現した場所ではなく今いる場所で決まることを保証する。"""

from pathlib import Path

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

# 廃坑の山村は、player 1・2 が spot 1、player 3・4 が spot 9 に出現する。
_SCENARIO = Path("data/scenarios/mine_village_v1.json")


def _executor(runtime) -> SpotGraphToolExecutor:
    services = SpotGraphWorldServices(
        interaction=runtime._interaction_service,
        exploration=runtime._exploration_service,
        world_flags=runtime._world_flag_state,
        game_end_evaluator=GameEndConditionEvaluator(),
        exploration_progress=runtime._exploration_progress,
        movement=runtime._movement_service,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=runtime._player_inventory_repo,
        item_repository=runtime._item_repo,
        event_publisher=runtime._speech_event_publisher,
        player_status_repository=runtime._player_status_repo,
        spot_graph_repository=runtime._spot_graph_repo,
        speech_service=runtime._speech_service,
        tend_to_player_command_scope_factory=runtime._tend_to_player_command_scope_factory,
        runtime=runtime,
    )


def _travel(runtime, player_id: int, destination: int) -> None:
    runtime._movement_service.start_travel_to_spot(
        PlayerId(player_id), SpotId.create(destination), frozenset(), frozenset()
    )
    runtime.advance_until_player_idle(PlayerId(player_id))


def _spot_of(runtime, player_id: int) -> int:
    return int(runtime._spot_graph_repo.find_graph().get_entity_spot(EntityId.create(player_id)))


def _down(runtime, player_id: int) -> None:
    status = runtime._player_status_repo.find_by_id(PlayerId(player_id))
    status.apply_damage(status.hp.value)
    events = tuple(status.get_events())
    status.clear_events()
    runtime._player_status_repo.save(status)
    runtime._speech_event_publisher.publish_all(events)
    tick = int(runtime.current_tick())
    runtime._fallen_body_registry.record(
        PlayerId(player_id), SpotId.create(_spot_of(runtime, player_id)), WorldTick(tick)
    )
    runtime._death_grace_timer.register(PlayerId(player_id), downed_at_tick=tick)


def _tend(runtime, actor: int, target: int):
    return _executor(runtime)._tend_to_player(
        actor,
        {"target_player_id": target, "target_display_name": "仲間", "inner_thought": "助ける"},
    )


def test_tending_succeeds_when_players_spawned_apart_now_share_a_spot() -> None:
    """別の場所に出現した人が、倒れた人のいる場所まで歩いてくれば、介抱して起こせる。"""
    runtime = create_world_runtime(_SCENARIO)
    _travel(runtime, 3, 1)
    _down(runtime, 1)
    assert _spot_of(runtime, 3) == _spot_of(runtime, 1) == 1

    result = _tend(runtime, 3, 1)

    assert result.success is True, result.message
    assert runtime._player_status_repo.find_by_id(PlayerId(1)).is_down is False


def test_tending_is_refused_when_players_spawned_together_are_now_apart() -> None:
    """同じ場所に出現した 2 人でも、倒れた人が別の場所にいれば、介抱は同席していないとして断られる。"""
    runtime = create_world_runtime(_SCENARIO)
    _travel(runtime, 1, 9)
    _down(runtime, 1)
    assert _spot_of(runtime, 2) != _spot_of(runtime, 1)

    result = _tend(runtime, 2, 1)

    assert result.success is False
    assert "同じ場所" in result.message
    assert runtime._player_status_repo.find_by_id(PlayerId(1)).is_down is True
