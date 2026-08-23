"""探索が発見状態・付与品・探索回数・観測を一つの確定単位にする契約。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_graph.spot_exploration_application_service import (
    SpotExplorationApplicationService,
)
from ai_rpg_world.application.world_graph.spot_exploration_progress_store import (
    InMemorySpotExplorationProgressStore,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.application.world_graph.overflow_sinks import GroundOverflowSink
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import (
    DiscoveryConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerOverflowedItemEvent,
    SpotExploredEvent,
)
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import (
    DiscoverableItem,
)
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import (
    DiscoveryCondition,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_interaction_command_repository_provider import (
    InMemoryInteractionCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
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
    build_exploration_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


PLAYER_ID = PlayerId(1)
SPOT_ID = SpotId.create(1)
SPEC_ID = ItemSpecId(101)


class _ItemSpecRepository:
    def find_by_id(self, item_spec_id: ItemSpecId) -> ItemSpec:
        return ItemSpec(
            item_spec_id=item_spec_id,
            name="埋もれた鍵",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="探索で見つかる鍵",
            max_stack_size=MaxStackSize(1),
        )


def _build_service(*, inventory_slots: int = 20) -> tuple[
    SpotExplorationApplicationService,
    InMemoryDataStore,
    InMemorySpotExplorationProgressStore,
    InMemorySpotInteriorRepository,
    list[object],
]:
    store = InMemoryDataStore()
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(
        SpotNode(
            spot_id=SPOT_ID,
            name="部屋",
            description="",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
        )
    )
    graph.place_entity(EntityId.create(1), SPOT_ID)
    graph.clear_events()
    graph_repository = InMemorySpotGraphRepository(graph)
    interior_repository = InMemorySpotInteriorRepository(data_store=store)
    interior_repository.save(
        SPOT_ID,
        SpotInterior.empty().replace_discoverable_items(
            (
                DiscoverableItem(
                    item_spec_id=SPEC_ID,
                    discovery_condition=DiscoveryCondition(
                        condition_type=DiscoveryConditionTypeEnum.SEARCH_COUNT,
                        required_search_count=1,
                    ),
                    is_discovered=False,
                    description="鍵を見つけた",
                ),
            )
        ),
    )
    inventory_repository = InMemoryPlayerInventoryRepository(store)
    inventory_repository.save(
        PlayerInventoryAggregate.create_new_inventory(
            PLAYER_ID,
            max_slots=inventory_slots,
        )
    )
    item_repository = InMemoryItemRepository(store)
    item_specs = _ItemSpecRepository()
    progress = InMemorySpotExplorationProgressStore()
    observed: list[object] = []
    dispatcher = CommandEventDispatcher()
    dispatcher.register_after_commit(
        SpotExploredEvent,
        observed.append,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    dispatcher.register_after_commit(
        PlayerOverflowedItemEvent,
        observed.append,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    overflow_sink = GroundOverflowSink(
        spot_graph_repository=graph_repository,
        spot_interior_repository=interior_repository,
        item_repository=item_repository,
        item_spec_repository=item_specs,
    )
    scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(store),
            participants=build_exploration_rollback_participants(progress=progress),
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=InMemoryInteractionCommandRepositoryProviderFactory(
            spot_graph=graph_repository,
            item_specs=item_specs,
        ),
    )
    service = SpotExplorationApplicationService(
        spot_graph_repository=graph_repository,
        spot_interior_repository=interior_repository,
        player_inventory_repository=inventory_repository,
        item_repository=item_repository,
        item_spec_repository=item_specs,
        world_flag_state=MutableWorldFlagState(),
        exploration_progress_store=progress,
        overflow_sink=overflow_sink,
        command_scope_factory=scope_factory,
    )
    return service, store, progress, interior_repository, observed


def test_success_observation_sees_committed_discovery_and_item() -> None:
    """探索観測は発見状態と付与品がともに確定した後にだけ配送される。"""
    service, store, _progress, interiors, observed = _build_service()

    result = service.explore_once(PLAYER_ID)

    assert result.item_spec_ids_granted == (SPEC_ID,)
    assert interiors.find_by_spot_id(SPOT_ID).discoverable_items[0].is_discovered
    assert len(store.items) == 1
    assert len(observed) == 1


def test_inventory_save_failure_rolls_back_every_exploration_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """付与品の所持保存失敗は探索回数・発見・品物を戻し、観測を出さない。"""
    service, store, progress, interiors, observed = _build_service()
    original_save = InMemoryPlayerInventoryRepository.save
    calls = 0

    def fail_grant_save(self, inventory):
        nonlocal calls
        calls += 1
        result = original_save(self, inventory)
        if calls == 1:
            raise RuntimeError("inventory grant failed")
        return result

    monkeypatch.setattr(InMemoryPlayerInventoryRepository, "save", fail_grant_save)

    with pytest.raises(RuntimeError, match="inventory grant failed"):
        service.explore_once(PLAYER_ID)

    assert not interiors.find_by_spot_id(SPOT_ID).discoverable_items[0].is_discovered
    assert store.items == {}
    assert progress.rollback_snapshot() == {}
    assert observed == []


def test_full_inventory_places_reward_on_ground_and_observes_after_commit() -> None:
    """満杯時は報酬を足元へ残し、溢れ観測も同じcommit後に一度だけ配送する。"""
    service, store, _progress, interiors, observed = _build_service(
        inventory_slots=0
    )

    service.explore_once(PLAYER_ID)

    interior = interiors.find_by_spot_id(SPOT_ID)
    assert interior.discoverable_items[0].is_discovered
    assert len(interior.ground_items) == 1
    assert len(store.items) == 1
    assert [type(event) for event in observed] == [
        PlayerOverflowedItemEvent,
        SpotExploredEvent,
    ]


def test_world_runtime_delivers_one_exploration_event_without_graph_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本番入口は探索eventを二重生成せず、確定後経路から一件だけ配送する。"""
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    runtime = create_world_runtime(
        Path("data/scenarios/survival_island_v4_coop.json"),
        config=ResolvedLlmRuntimeConfig.for_tests(),
    )
    player_id = runtime.get_player_ids()[0]
    delivered: list[SpotExploredEvent] = []
    original_publish_all = runtime._speech_event_publisher.publish_all

    def capture(events):
        delivered.extend(
            event for event in events if isinstance(event, SpotExploredEvent)
        )
        return original_publish_all(events)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", capture)

    runtime.do_explore(player_id)

    assert len(delivered) == 1
    assert delivered[0].entity_id == EntityId.create(int(player_id))
    assert delivered[0].spot_id == runtime._spot_graph_repo.find_graph().get_entity_spot(
        EntityId.create(int(player_id))
    )
    assert not any(
        isinstance(event, SpotExploredEvent)
        for event in runtime._spot_graph_repo.find_graph().get_events()
    )
