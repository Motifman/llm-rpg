from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import create_spot_graph_world_services
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import InMemorySpotGraphRepository
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from tests.domain.player.aggregate.test_player_status_aggregate import create_test_status_aggregate


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _graph_with_locked_connection() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(5),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="door",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.door(DoorStateEnum.LOCKED),
        )
    )
    g.place_entity(EntityId.create(1), SpotId.create(1))
    g.clear_events()
    return g


def _switch_interior() -> SpotInterior:
    obj = SpotObject(
        object_id=SpotObjectId.create(2),
        name="Switch",
        description="",
        object_type=SpotObjectTypeEnum.SWITCH,
        state={},
        interactions=(
            InteractionDef(
                action_name="use",
                display_label="押す",
                preconditions=(InteractionCondition(condition_type=InteractionConditionTypeEnum.ALWAYS),),
                effects=(
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.SET_FLAG,
                        parameters={"flag_name": "power_on"},
                    ),
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.CHANGE_PASSAGE_STATE,
                        parameters={"connection_id": 5, "new_state": "OPEN"},
                    ),
                ),
            ),
        ),
    )
    return SpotInterior((), (obj,), (), ())


class _StubItemSpecRepo:
    """ItemSpecId(101) のみ返すスタブ（GIVE_ITEM テスト用）。"""

    def find_by_id(self, item_spec_id: ItemSpecId):
        if item_spec_id != ItemSpecId(101):
            return None
        return ItemSpec(
            item_spec_id=ItemSpecId(101),
            name="Test",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="test",
            max_stack_size=MaxStackSize(99),
        )


def test_interaction_sets_flag_and_unlocks_connection() -> None:
    graph = _graph_with_locked_connection()
    graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository({SpotId.create(1): _switch_interior()})
    store = InMemoryDataStore()
    player_repo = InMemoryPlayerStatusRepository(store)
    inv_repo = InMemoryPlayerInventoryRepository(store)
    player_repo.save(create_test_status_aggregate(player_id=1))
    inv_repo.save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))

    flags = MutableWorldFlagState()
    svc = SpotInteractionApplicationService(
        spot_graph_repository=graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inv_repo,
        item_repository=InMemoryItemRepository(store),
        item_spec_repository=_StubItemSpecRepo(),
        world_flag_state=flags,
    )

    r = svc.execute_interaction(PlayerId(1), SpotObjectId.create(2), "use")
    assert "power_on" in flags.as_frozen_set()
    assert graph_repo.find_graph().get_connection(ConnectionId.create(5)).passage.traversable is True
    assert r.messages == ()


def test_interaction_propagates_actor_to_connection_state_event() -> None:
    """Issue #183: interaction 経由の passage 変化は ConnectionStateChangedEvent
    の original_actor_entity_id に actor を伝播する (軸 1+4)。

    SpotInteractionApplicationService は ``graph.get_events()`` で集めた
    domain event を ``event_publisher.publish_all`` 経由で送り出すので、
    publisher を inject してそこに流れた event を検査する。
    """
    from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
        PassageChangeCauseEnum,
    )
    from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
        ConnectionStateChangedEvent,
    )

    graph = _graph_with_locked_connection()
    graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository({SpotId.create(1): _switch_interior()})
    store = InMemoryDataStore()
    player_repo = InMemoryPlayerStatusRepository(store)
    inv_repo = InMemoryPlayerInventoryRepository(store)
    player_repo.save(create_test_status_aggregate(player_id=1))
    inv_repo.save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))

    published: list = []

    class _CapturingPublisher:
        def publish(self, event):
            published.append(event)

        def publish_all(self, events):
            published.extend(events)

    flags = MutableWorldFlagState()
    svc = SpotInteractionApplicationService(
        spot_graph_repository=graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inv_repo,
        item_repository=InMemoryItemRepository(store),
        item_spec_repository=_StubItemSpecRepo(),
        world_flag_state=flags,
        event_publisher=_CapturingPublisher(),
    )

    svc.execute_interaction(PlayerId(1), SpotObjectId.create(2), "use")
    conn_events = [
        e for e in published if isinstance(e, ConnectionStateChangedEvent)
    ]
    assert len(conn_events) == 1
    # cause は ACTOR_ACTION (PR #182 で設定済み)
    assert conn_events[0].cause == PassageChangeCauseEnum.ACTOR_ACTION
    # 軸 1+4: 起点 actor (PlayerId=1) が EntityId として乗る
    assert conn_events[0].original_actor_entity_id is not None
    assert conn_events[0].original_actor_entity_id.value == 1


def test_create_spot_graph_world_services_bundle() -> None:
    graph = _graph_with_locked_connection()
    graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository({SpotId.create(1): _switch_interior()})
    store = InMemoryDataStore()
    player_repo = InMemoryPlayerStatusRepository(store)
    inv_repo = InMemoryPlayerInventoryRepository(store)
    player_repo.save(create_test_status_aggregate(player_id=1))
    inv_repo.save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))

    bundle = create_spot_graph_world_services(
        spot_graph_repository=graph_repo,
        spot_interior_repository=interior_repo,
        player_status_repository=player_repo,
        player_inventory_repository=inv_repo,
        item_repository=InMemoryItemRepository(store),
        item_spec_repository=_StubItemSpecRepo(),
    )
    assert bundle.interaction is not None
    assert bundle.exploration is not None
    assert bundle.game_end_evaluator is not None


def test_exploration_discovers_and_grants_item() -> None:
    from ai_rpg_world.application.world_graph.spot_exploration_application_service import (
        SpotExplorationApplicationService,
    )
    from ai_rpg_world.application.world_graph.spot_exploration_progress_store import (
        InMemorySpotExplorationProgressStore,
    )

    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(_node(1))
    graph.place_entity(EntityId.create(1), SpotId.create(1))
    graph.clear_events()

    d = DiscoverableItem(
        item_spec_id=ItemSpecId(101),
        discovery_condition=DiscoveryCondition(
            condition_type=DiscoveryConditionTypeEnum.SEARCH_COUNT,
            required_search_count=1,
        ),
        is_discovered=False,
        description="見つけた",
    )
    interior = SpotInterior.empty().replace_discoverable_items((d,))
    graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository({SpotId.create(1): interior})
    store = InMemoryDataStore()
    player_repo = InMemoryPlayerStatusRepository(store)
    inv_repo = InMemoryPlayerInventoryRepository(store)
    player_repo.save(create_test_status_aggregate(player_id=1))
    inv_repo.save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))

    progress = InMemorySpotExplorationProgressStore()
    exp_svc = SpotExplorationApplicationService(
        spot_graph_repository=graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inv_repo,
        item_repository=InMemoryItemRepository(store),
        item_spec_repository=_StubItemSpecRepo(),
        world_flag_state=MutableWorldFlagState(),
        exploration_progress_store=progress,
    )
    result = exp_svc.explore_once(PlayerId(1))
    assert len(result.discovery_descriptions) == 1
    assert ItemSpecId(101) in result.item_spec_ids_granted
    inv2 = inv_repo.find_by_id(PlayerId(1))
    assert inv2 is not None
    assert any(inv2.get_item_instance_id_by_slot(SlotId(i)) is not None for i in range(inv2.max_slots))
