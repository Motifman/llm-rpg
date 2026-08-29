"""monster spawnがslot 1件ごとに状態と観測を確定する契約。"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_graph.spot_graph_monster_spawn_stage_service import (
    MonsterSpawnSlot,
    SpotGraphMonsterSpawnStageService,
)
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_spawn_command_repository_provider import (
    InMemoryMonsterSpawnCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.in_memory_skill_loadout_repository import (
    InMemorySkillLoadoutRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
    build_monster_spawn_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)


SPOT_ID = SpotId.create(1)


def _template(template_id: int = 1) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(template_id),
        name=f"wolf-{template_id}",
        base_stats=BaseStats(30, 0, 8, 4, 6, 0.05, 0.1),
        reward_info=RewardInfo(exp=10, gold=0),
        respawn_info=RespawnInfo(respawn_interval_ticks=80, is_auto_respawn=False),
        race=Race.WOLF,
        faction=MonsterFactionEnum.ENEMY,
        description="scope test monster",
    )


def _slot(key: str, *, template_id: int = 1) -> MonsterSpawnSlot:
    return MonsterSpawnSlot(
        slot_key=key,
        template=_template(template_id),
        spot_id=SPOT_ID,
        coordinate=Coordinate(0, 0, 0),
        day_night_phase_names=(),
        required_flags=(),
        forbidden_flags=(),
        weather_type_names=(),
    )


def _graph() -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(
        SpotNode(
            spot_id=SPOT_ID,
            name="forest",
            description="",
            category=SpotCategoryEnum.FIELD,
            parent_id=None,
        )
    )
    graph.clear_events()
    return graph


@dataclass
class _Harness:
    stage: SpotGraphMonsterSpawnStageService
    store: InMemoryDataStore
    monsters: InMemoryMonsterAggregateRepository
    loadouts: InMemorySkillLoadoutRepository
    graph: InMemorySpotGraphRepository
    observed: list[tuple[str, int, int, tuple[str, ...]]]


def _build(slots: tuple[MonsterSpawnSlot, ...]) -> _Harness:
    store = InMemoryDataStore()
    monsters = InMemoryMonsterAggregateRepository(store)
    loadouts = InMemorySkillLoadoutRepository(store)
    graph = InMemorySpotGraphRepository(_graph())
    stage = SpotGraphMonsterSpawnStageService(
        slots=slots,
        monster_repository=monsters,
        skill_loadout_repository=loadouts,
        spot_graph_repository=graph,
    )
    observed: list[tuple[str, int, int, tuple[str, ...]]] = []
    dispatcher = CommandEventDispatcher()

    def observe(event: BaseDomainEvent) -> None:
        observed.append(
            (
                type(event).__name__,
                len(monsters.find_all()),
                len(loadouts.find_all()),
                tuple(stage.active_slot_keys()),
            )
        )

    dispatcher.register_after_commit(
        BaseDomainEvent,
        observe,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(store),
            participants=build_monster_spawn_rollback_participants(
                spot_graph=graph,
                stage=stage,
            ),
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=(
            InMemoryMonsterSpawnCommandRepositoryProviderFactory(spot_graph=graph)
        ),
    )
    stage.set_command_scope_factory(scope_factory)
    return _Harness(stage, store, monsters, loadouts, graph, observed)


def test_spawn_commits_all_resources_before_observation() -> None:
    """出現観測時点でmonster・loadout・graph・slot対応がすべて確定している。"""
    harness = _build((_slot("wolf#0"),))

    harness.stage.run(WorldTick(1))

    monsters = harness.monsters.find_all()
    loadouts = harness.loadouts.find_all()
    assert [monster.monster_id.value for monster in monsters] == [10_001]
    assert [loadout.loadout_id.value for loadout in loadouts] == [20_001]
    assert tuple(harness.graph.find_graph().monster_spot_mapping()) == (
        monsters[0].monster_id,
    )
    assert harness.stage.active_slot_keys() == ["wolf#0"]
    assert harness.observed == [
        ("MonsterAppearedAtSpotEvent", 1, 1, ("wolf#0",))
    ]


def test_spawn_failure_rolls_back_resources_events_and_identifiers() -> None:
    """graph保存失敗では全資源と観測を戻し、再試行も同じIDを使う。"""
    harness = _build((_slot("wolf#0"),))
    original_save = harness.graph.save
    calls = 0

    def fail_first_save(graph: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("graph save failed")
        original_save(graph)

    harness.graph.save = fail_first_save  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="graph save failed"):
        harness.stage.run(WorldTick(1))

    assert harness.monsters.find_all() == []
    assert harness.loadouts.find_all() == []
    assert harness.graph.find_graph().monster_spot_mapping() == {}
    assert harness.stage.active_slot_keys() == []
    assert harness.observed == []

    harness.graph.save = original_save  # type: ignore[method-assign]
    harness.stage.run(WorldTick(2))
    assert [monster.monster_id.value for monster in harness.monsters.find_all()] == [
        10_001
    ]
    assert [loadout.loadout_id.value for loadout in harness.loadouts.find_all()] == [
        20_001
    ]


def test_each_slot_commits_independently() -> None:
    """後続slotの失敗は先に確定したslotの出現を巻き戻さない。"""
    harness = _build((_slot("wolf#0"), _slot("wolf#1", template_id=2)))
    original_save = harness.graph.save
    calls = 0

    def fail_second_save(graph: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second slot failed")
        original_save(graph)

    harness.graph.save = fail_second_save  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="second slot failed"):
        harness.stage.run(WorldTick(1))

    assert [monster.monster_id.value for monster in harness.monsters.find_all()] == [
        10_001
    ]
    assert [loadout.loadout_id.value for loadout in harness.loadouts.find_all()] == [
        20_001
    ]
    assert harness.stage.active_slot_keys() == ["wolf#0"]
    assert [entry[0] for entry in harness.observed] == [
        "MonsterAppearedAtSpotEvent"
    ]


def test_spawn_collects_only_events_created_by_its_slot() -> None:
    """先行stageのgraph eventを残し、このslotが追加したeventだけを配送する。"""
    harness = _build((_slot("wolf#0"),))
    graph = harness.graph.find_graph()
    graph.place_monster(MonsterId(999), SPOT_ID)
    preexisting_events = tuple(graph.get_events())
    harness.graph.save(graph)

    harness.stage.run(WorldTick(1))

    assert [entry[0] for entry in harness.observed] == [
        "MonsterAppearedAtSpotEvent"
    ]
    assert tuple(harness.graph.find_graph().get_events()) == preexisting_events


def test_despawn_failure_restores_graph_slot_and_observation() -> None:
    """despawn保存失敗では配置とslot対応を保ち、退出観測を配送しない。"""
    cell = {"enabled": True}
    slot = _slot("wolf#0")
    slot = MonsterSpawnSlot(
        slot_key=slot.slot_key,
        template=slot.template,
        spot_id=slot.spot_id,
        coordinate=slot.coordinate,
        day_night_phase_names=(),
        required_flags=("enabled",),
        forbidden_flags=(),
        weather_type_names=(),
    )
    harness = _build((slot,))
    harness.stage._flags_provider = lambda: (
        frozenset({"enabled"}) if cell["enabled"] else frozenset()
    )
    harness.stage.run(WorldTick(1))
    harness.observed.clear()
    original_save = harness.graph.save
    calls = 0

    def fail_first_save(graph: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("despawn save failed")
        original_save(graph)

    harness.graph.save = fail_first_save  # type: ignore[method-assign]
    cell["enabled"] = False

    with pytest.raises(RuntimeError, match="despawn save failed"):
        harness.stage.run(WorldTick(2))

    assert harness.stage.active_slot_keys() == ["wolf#0"]
    assert len(harness.graph.find_graph().monster_spot_mapping()) == 1
    assert harness.observed == []


def test_scoped_stage_rejects_external_identifier_factories() -> None:
    """rollback不能な外部採番をscopeへ接続すると開始前に拒否する。"""
    stage = SpotGraphMonsterSpawnStageService(
        slots=(_slot("wolf#0"),),
        monster_repository=InMemoryMonsterAggregateRepository(),
        skill_loadout_repository=InMemorySkillLoadoutRepository(),
        spot_graph_repository=InMemorySpotGraphRepository(_graph()),
        monster_id_factory=lambda: 1,
    )

    with pytest.raises(ValueError, match="外部ID factory"):
        stage.set_command_scope_factory(object())  # type: ignore[arg-type]
    assert stage._command_scope_factory is None
