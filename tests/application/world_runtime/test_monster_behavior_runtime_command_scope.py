"""本番monster behaviorが1体ごとの確定境界を使う契約。"""

import random
from pathlib import Path

import pytest

from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


SCENARIO = Path("data/scenarios/survival_island_v2.json")


def _runtime_attack_setup():
    runtime = create_world_runtime(SCENARIO)
    service = runtime._simulation_service._monster_behavior_stage._service
    player_id = PlayerId(runtime.scenario.player_spawns[0].player_id)
    spot_id = SpotId.create(runtime.id_mapper.get_int("spot", "plane_wreck"))
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(player_id.value)
    graph.unplace_entity(entity_id)
    graph.place_entity(entity_id, spot_id)
    graph.clear_events()
    runtime._spot_graph_repo.save(graph)
    monster_id = next(
        iter(
            runtime._spot_graph_repo.find_graph()
            .monster_presence_at(spot_id)
            .present_monster_ids
        )
    )
    return runtime, service, player_id, monster_id, spot_id


def test_runtime_wires_one_monster_command_scope() -> None:
    """monsterが存在する本番runtimeはbehavior serviceへscopeを接続する。"""
    runtime = create_world_runtime(SCENARIO)
    service = runtime._simulation_service._monster_behavior_stage._service

    assert service._command_scope_factory is not None
    shared_store = runtime._monster_repo._data_store
    assert runtime._player_status_repo._data_store is shared_store
    transaction_factory = service._command_scope_factory._transaction_factory
    assert transaction_factory._transaction_factory._data_store is shared_store


def test_attack_observation_sees_committed_monster_and_player() -> None:
    """攻撃eventの配送時点でplayer HPとmonster cooldownが確定している。"""
    runtime, service, player_id, monster_id, _ = _runtime_attack_setup()
    observed: list[tuple[str, int, int | None]] = []
    dispatcher = service._command_scope_factory._after_commit_handoff

    def observe(event: BaseDomainEvent) -> None:
        player = runtime._player_status_repo.find_by_id(player_id)
        monster = runtime._monster_repo.find_by_id(monster_id)
        assert player is not None
        assert monster is not None
        observed.append(
            (
                type(event).__name__,
                player.hp.value,
                (
                    monster.last_attack_tick.value
                    if monster.last_attack_tick is not None
                    else None
                ),
            )
        )

    dispatcher.register_after_commit(
        BaseDomainEvent,
        observe,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    outcomes = service.tick(WorldTick(10))

    assert len(outcomes) == 1
    assert outcomes[0].executed is True
    assert observed == [
        ("MonsterAttackedPlayerInSpotEvent", 100 - outcomes[0].damage, 10)
    ]


def test_graph_save_failure_rolls_back_attack_event_and_randomness() -> None:
    """攻撃後のgraph保存失敗は二者状態・観測・乱数列を開始前へ戻す。"""
    runtime, service, player_id, monster_id, _ = _runtime_attack_setup()
    player_before = runtime._player_status_repo.find_by_id(player_id)
    monster_before = runtime._monster_repo.find_by_id(monster_id)
    graph_before = runtime._spot_graph_repo.find_graph()
    monster_mapping_before = dict(graph_before.monster_spot_mapping())
    entity_mapping_before = dict(graph_before.entity_spot_mapping())
    graph_events_before = tuple(graph_before.get_events())
    random_before = service._random.getstate()
    module_random_before = random.getstate()
    assert player_before is not None
    assert monster_before is not None
    observed: list[str] = []
    dispatcher = service._command_scope_factory._after_commit_handoff
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: observed.append(type(event).__name__),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    original_save = runtime._spot_graph_repo.save
    calls = 0

    def fail_first_save(graph) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("behavior graph save failed")
        original_save(graph)

    runtime._spot_graph_repo.save = fail_first_save

    with pytest.raises(RuntimeError, match="behavior graph save failed"):
        service.tick(WorldTick(10))

    player_after = runtime._player_status_repo.find_by_id(player_id)
    monster_after = runtime._monster_repo.find_by_id(monster_id)
    graph_after = runtime._spot_graph_repo.find_graph()
    assert player_after is not None
    assert monster_after is not None
    assert player_after.hp == player_before.hp
    assert monster_after.last_attack_tick == monster_before.last_attack_tick
    assert graph_after.monster_spot_mapping() == monster_mapping_before
    assert graph_after.entity_spot_mapping() == entity_mapping_before
    assert tuple(graph_after.get_events()) == graph_events_before
    assert service._random.getstate() == random_before
    assert random.getstate() == module_random_before
    assert observed == []
