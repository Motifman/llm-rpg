"""drop/pickupが所持品と地面を一つの確定境界で扱う契約。"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    SpotGraphItemTransferService,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerDroppedItemEvent,
    PlayerPickedUpItemEvent,
)
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_transfer_command_repository_provider import (  # noqa: E501
    InMemoryItemTransferCommandRepositoryProviderFactory,
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
from tests.application.world_graph.test_spot_graph_item_transfer_service import (
    PLAYER_ID,
    SPOT_ID,
    _make_graph_with_player,
    _make_item_spec,
)


class _FailAfterInteriorSave:
    """地面の変更を行った直後に失敗させ、snapshot rollbackを検証する。"""

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate

    def find_by_spot_id(self, spot_id):
        return self._delegate.find_by_spot_id(spot_id)

    def save(self, spot_id, interior) -> None:
        self._delegate.save(spot_id, interior)
        raise RuntimeError("interior save failed")


class _FailingProvider:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self._spot_interiors = _FailAfterInteriorSave(delegate.spot_interiors)

    @property
    def player_inventories(self):
        return self._delegate.player_inventories

    @property
    def player_statuses(self):
        return self._delegate.player_statuses

    @property
    def items(self):
        return self._delegate.items

    @property
    def spot_graph(self):
        return self._delegate.spot_graph

    @property
    def spot_interiors(self):
        return self._spot_interiors


class _FailingProviderFactory:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate

    def create(self, context: object, transaction: object):
        return _FailingProvider(self._delegate.create(context, transaction))


@dataclass(frozen=True)
class _CommitObservation:
    event_type: type[object]
    inventory_item_present: bool
    ground_item_present: bool


def _build_service(
    *, fail_interior_save: bool = False, item_on_ground: bool = False
):
    store = InMemoryDataStore()
    inventories = InMemoryPlayerInventoryRepository(store)
    items = InMemoryItemRepository(store)
    interiors = InMemorySpotInteriorRepository(data_store=store)
    graph = InMemorySpotGraphRepository(_make_graph_with_player(SPOT_ID, (PLAYER_ID,)))

    item = ItemAggregate.create(
        items.generate_item_instance_id(), _make_item_spec(), quantity=1
    )
    items.save(item)
    inventory = PlayerInventoryAggregate.create_new_inventory(PLAYER_ID)
    if not item_on_ground:
        inventory.acquire_item(
            item.item_instance_id,
            item_spec_id_value=item.item_spec.item_spec_id.value,
        )
    inventories.save(inventory)
    interior = SpotInterior.empty()
    if item_on_ground:
        interior = interior.with_ground_item(
            GroundItem(
                item_instance_id=item.item_instance_id,
                item_spec_id=item.item_spec.item_spec_id,
            )
        )
    interiors.save(SPOT_ID, interior)

    observations: list[_CommitObservation] = []
    dispatcher = CommandEventDispatcher()

    def observe_committed(event: object) -> None:
        committed_inventory = inventories.find_by_id(PLAYER_ID)
        committed_interior = interiors.find_by_spot_id(SPOT_ID)
        observations.append(
            _CommitObservation(
                event_type=type(event),
                inventory_item_present=(
                    committed_inventory.get_item_instance_id_by_slot(SlotId(0))
                    == item.item_instance_id
                ),
                ground_item_present=(
                    committed_interior.find_ground_item(item.item_instance_id)
                    is not None
                ),
            )
        )

    for event_type in (PlayerDroppedItemEvent, PlayerPickedUpItemEvent):
        dispatcher.register_after_commit(
            event_type,
            observe_committed,
            channel=DeliveryChannel.OBSERVATION,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
        )

    provider_factory: object = InMemoryItemTransferCommandRepositoryProviderFactory(
        graph
    )
    if fail_interior_save:
        provider_factory = _FailingProviderFactory(provider_factory)
    scope_factory = CommandScopeFactory(
        InMemoryUnitOfWorkTransactionFactory(store),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=provider_factory,
    )
    service = SpotGraphItemTransferService(
        spot_graph_repository=graph,
        player_inventory_repository=inventories,
        spot_interior_repository=interiors,
        item_repository=items,
        item_transfer_command_scope_factory=scope_factory,
    )
    return service, inventories, interiors, item.item_instance_id, observations


def test_drop_commits_inventory_and_ground_before_observation() -> None:
    """drop成功時は所持品と地面を確定してから観測を配送する。"""
    service, inventories, interiors, item_id, observations = _build_service()

    service.drop_item(PLAYER_ID, SlotId(0))

    assert inventories.find_by_id(PLAYER_ID).get_item_instance_id_by_slot(SlotId(0)) is None
    assert interiors.find_by_spot_id(SPOT_ID).find_ground_item(item_id) is not None
    assert observations == [
        _CommitObservation(PlayerDroppedItemEvent, False, True)
    ]


def test_drop_interior_failure_rolls_back_inventory_ground_and_observation() -> None:
    """dropの地面保存失敗時は所持品も地面も戻して観測を出さない。"""
    service, inventories, interiors, item_id, observations = _build_service(
        fail_interior_save=True
    )

    with pytest.raises(RuntimeError, match="interior save failed"):
        service.drop_item(PLAYER_ID, SlotId(0))

    assert inventories.find_by_id(PLAYER_ID).get_item_instance_id_by_slot(SlotId(0)) == item_id
    assert interiors.find_by_spot_id(SPOT_ID).find_ground_item(item_id) is None
    assert observations == []


def test_pickup_commits_inventory_and_ground_before_observation() -> None:
    """pickup成功時は取得と地面除去を確定してから観測を配送する。"""
    service, inventories, interiors, item_id, observations = _build_service(
        item_on_ground=True
    )

    service.pickup_item(PLAYER_ID, item_id)

    assert inventories.find_by_id(PLAYER_ID).get_item_instance_id_by_slot(SlotId(0)) == item_id
    assert interiors.find_by_spot_id(SPOT_ID).find_ground_item(item_id) is None
    assert observations == [
        _CommitObservation(PlayerPickedUpItemEvent, True, False)
    ]


def test_pickup_interior_failure_rolls_back_inventory_ground_and_observation() -> None:
    """pickupの地面保存失敗時は取得を戻して地面アイテムを維持する。"""
    service, inventories, interiors, item_id, observations = _build_service(
        fail_interior_save=True,
        item_on_ground=True,
    )

    with pytest.raises(RuntimeError, match="interior save failed"):
        service.pickup_item(PLAYER_ID, item_id)

    assert inventories.find_by_id(PLAYER_ID).get_item_instance_id_by_slot(SlotId(0)) is None
    assert interiors.find_by_spot_id(SPOT_ID).find_ground_item(item_id) is not None
    assert observations == []
