"""monster行動scopeが採食の複数資源を一括確定する契約。"""

import random

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
    SpotMonsterBehaviorTickService,
)
from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
    SkillLoadoutAggregate,
)
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAteGroundItemEvent,
)
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_behavior_command_repository_provider import (
    InMemoryMonsterBehaviorCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
    build_monster_behavior_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)


SPOT_ID = SpotId.create(1)
MEAT_SPEC = ItemSpecId(99)


def _template() -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="wolf",
        base_stats=BaseStats(10, 0, 2, 0, 1, 0.0, 0.0),
        reward_info=RewardInfo(exp=1, gold=0),
        respawn_info=RespawnInfo(100, False),
        race=Race.WOLF,
        faction=MonsterFactionEnum.NEUTRAL,
        description="forage scope test",
        starvation_ticks=10,
        hunger_increase_per_tick=0.6,
        forage_threshold=0.5,
        hunger_decrease_on_feed=0.4,
        preferred_feed_item_spec_ids=frozenset({MEAT_SPEC}),
        idle_wander_chance=0.0,
    )


def _build():
    store = InMemoryDataStore()
    monsters = InMemoryMonsterAggregateRepository(store)
    players = InMemoryPlayerStatusRepository(store)
    interiors = InMemorySpotInteriorRepository(data_store=store)
    graph_value = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph_value.add_spot(
        SpotNode(
            spot_id=SPOT_ID,
            name="field",
            description="",
            category=SpotCategoryEnum.FIELD,
            parent_id=None,
        )
    )
    graph = InMemorySpotGraphRepository(graph_value)
    monster = MonsterAggregate(
        monster_id=MonsterId.create(101),
        template=_template(),
        world_object_id=WorldObjectId.create(9001),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=101, normal_capacity=0, awakened_capacity=0
        ),
        status=MonsterStatusEnum.ALIVE,
        coordinate=Coordinate(0, 0, 0),
        spot_id=SPOT_ID,
        spawned_at_tick=WorldTick(0),
    )
    monsters.save(monster)
    graph_value = graph.find_graph()
    graph_value.place_monster(monster.monster_id, SPOT_ID)
    graph_value.clear_events()
    graph.save(graph_value)
    interiors.save(
        SPOT_ID,
        SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(GroundItem(ItemInstanceId(1), MEAT_SPEC),),
            discoverable_items=(),
        ),
    )
    random_source = random.Random(7)
    service = SpotMonsterBehaviorTickService(
        graph,
        monsters,
        players,
        SpotAttackOrchestrator(graph, monsters, players),
        random_source=random_source,
        spot_interior_repository=interiors,
    )
    observed: list[tuple[str, float, int]] = []
    dispatcher = CommandEventDispatcher()

    def observe(event: BaseDomainEvent) -> None:
        committed_monster = monsters.find_by_id(monster.monster_id)
        committed_interior = interiors.find_by_spot_id(SPOT_ID)
        assert committed_monster is not None
        assert committed_interior is not None
        observed.append(
            (
                type(event).__name__,
                committed_monster.hunger,
                len(committed_interior.ground_items),
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
            participants=build_monster_behavior_rollback_participants(
                spot_graph=graph,
                service=service,
            ),
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=(
            InMemoryMonsterBehaviorCommandRepositoryProviderFactory(
                spot_graph=graph
            )
        ),
    )
    service.set_command_scope_factory(scope_factory)
    return service, monsters, interiors, graph, observed


def test_forage_observation_sees_committed_hunger_and_ground_item() -> None:
    """採食観測時点で空腹回復と地面item除去がともに確定している。"""
    service, _, _, graph, observed = _build()
    preexisting_event = MonsterAteGroundItemEvent.create(
        aggregate_id=graph.find_graph().graph_id,
        aggregate_type="SpotGraphAggregate",
        monster_id=MonsterId.create(999),
        spot_id=SPOT_ID,
        item_instance_id=ItemInstanceId(999),
        item_spec_id=MEAT_SPEC,
    )
    graph_value = graph.find_graph()
    graph_value.add_event(preexisting_event)
    graph.save(graph_value)

    service.tick(WorldTick(1))

    assert observed == [("MonsterAteGroundItemEvent", pytest.approx(0.2), 0)]
    assert graph.find_graph().get_events() == [preexisting_event]


def test_forage_graph_save_failure_rolls_back_all_resources() -> None:
    """採食後のgraph保存失敗は空腹・地面item・観測・乱数列を戻す。"""
    service, monsters, interiors, graph, observed = _build()
    random_before = service._random.getstate()
    original_save = graph.save
    calls = 0

    def fail_first_save(value: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("forage graph save failed")
        original_save(value)

    graph.save = fail_first_save  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="forage graph save failed"):
        service.tick(WorldTick(1))

    monster = monsters.find_by_id(MonsterId.create(101))
    interior = interiors.find_by_spot_id(SPOT_ID)
    assert monster is not None
    assert interior is not None
    assert monster.hunger == 0.0
    assert [item.item_instance_id for item in interior.ground_items] == [
        ItemInstanceId(1)
    ]
    assert graph.find_graph().get_events() == []
    assert service._random.getstate() == random_before
    assert observed == []


def test_later_monster_failure_keeps_earlier_monster_commit() -> None:
    """後続monsterの失敗は先に確定した採食を巻き戻さない。"""
    service, monsters, interiors, graph, observed = _build()
    second = MonsterAggregate(
        monster_id=MonsterId.create(102),
        template=_template(),
        world_object_id=WorldObjectId.create(9002),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(2), owner_id=102, normal_capacity=0, awakened_capacity=0
        ),
        status=MonsterStatusEnum.ALIVE,
        coordinate=Coordinate(0, 0, 0),
        spot_id=SPOT_ID,
        spawned_at_tick=WorldTick(0),
    )
    monsters.save(second)
    graph_value = graph.find_graph()
    graph_value.place_monster(second.monster_id, SPOT_ID)
    graph_value.clear_events()
    graph.save(graph_value)
    interiors.save(
        SPOT_ID,
        SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(
                GroundItem(ItemInstanceId(1), MEAT_SPEC),
                GroundItem(ItemInstanceId(2), MEAT_SPEC),
            ),
            discoverable_items=(),
        ),
    )
    original_save = graph.save
    calls = 0

    def fail_second_save(value: SpotGraphAggregate) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second monster failed")
        original_save(value)

    graph.save = fail_second_save  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="second monster failed"):
        service.tick(WorldTick(1))

    first_after = monsters.find_by_id(MonsterId.create(101))
    second_after = monsters.find_by_id(MonsterId.create(102))
    interior_after = interiors.find_by_spot_id(SPOT_ID)
    assert first_after is not None
    assert second_after is not None
    assert interior_after is not None
    assert first_after.hunger == pytest.approx(0.2)
    assert second_after.hunger == 0.0
    assert [item.item_instance_id for item in interior_after.ground_items] == [
        ItemInstanceId(2)
    ]
    assert observed == [("MonsterAteGroundItemEvent", pytest.approx(0.2), 1)]
