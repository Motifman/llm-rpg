"""give_itemが2つの所持品更新と成功観測を1つの確定境界で扱う契約。"""

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
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import PlayerGaveItemEvent
from ai_rpg_world.infrastructure.events.command_event_dispatcher import CommandEventDispatcher
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_transfer_command_repository_provider import (
    InMemoryItemTransferCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
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
from tests.application.world_graph.test_spot_graph_item_transfer_service import (
    OTHER_PLAYER_ID,
    PLAYER_ID,
    SPOT_ID,
    _make_graph_with_player,
    _make_item_spec,
)
from tests.domain.player.aggregate.test_player_status_aggregate import (
    create_test_status_aggregate,
)


@dataclass
class _CommitObservation:
    sender_has_item: bool
    recipient_has_item: bool


class _FailOnSecondInventorySave:
    """2回目のsaveをUoWへ登録した直後に故障させるrepository。"""

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self._save_count = 0

    def find_by_id(self, player_id: PlayerId):
        return self._delegate.find_by_id(player_id)

    def save(self, inventory: PlayerInventoryAggregate):
        self._save_count += 1
        result = self._delegate.save(inventory)
        if self._save_count == 2:
            raise RuntimeError("recipient save failed")
        return result


class _FailingProvider:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self._inventories = _FailOnSecondInventorySave(delegate.player_inventories)

    @property
    def player_inventories(self):
        return self._inventories

    @property
    def player_statuses(self):
        return self._delegate.player_statuses

    @property
    def items(self):
        return self._delegate.items

    @property
    def spot_graph(self):
        return self._delegate.spot_graph


class _FailingProviderFactory:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate

    def create(self, context: object, transaction: object):
        return _FailingProvider(self._delegate.create(context, transaction))


def _build_scoped_service(*, fail_second_save: bool = False):
    data_store = InMemoryDataStore()
    inventories = InMemoryPlayerInventoryRepository(data_store)
    items = InMemoryItemRepository(data_store)
    statuses = InMemoryPlayerStatusRepository(data_store)
    graph = InMemorySpotGraphRepository(
        _make_graph_with_player(SPOT_ID, (PLAYER_ID, OTHER_PLAYER_ID))
    )
    item = ItemAggregate.create(
        items.generate_item_instance_id(), _make_item_spec(), quantity=1
    )
    items.save(item)
    sender = PlayerInventoryAggregate.create_new_inventory(PLAYER_ID)
    sender.acquire_item(
        item.item_instance_id,
        item_spec_id_value=item.item_spec.item_spec_id.value,
    )
    inventories.save(sender)
    inventories.save(PlayerInventoryAggregate.create_new_inventory(OTHER_PLAYER_ID))
    statuses.save(create_test_status_aggregate(player_id=PLAYER_ID.value))
    statuses.save(create_test_status_aggregate(player_id=OTHER_PLAYER_ID.value))

    observations: list[_CommitObservation] = []
    dispatcher = CommandEventDispatcher()

    def observe_committed(_: object) -> None:
        committed_sender = inventories.find_by_id(PLAYER_ID)
        committed_recipient = inventories.find_by_id(OTHER_PLAYER_ID)
        observations.append(
            _CommitObservation(
                sender_has_item=(
                    committed_sender.get_item_instance_id_by_slot(SlotId(0))
                    is not None
                ),
                recipient_has_item=(
                    committed_recipient.get_item_instance_id_by_slot(SlotId(0))
                    is not None
                ),
            )
        )

    dispatcher.register_after_commit(
        PlayerGaveItemEvent,
        observe_committed,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    provider_factory: object = InMemoryItemTransferCommandRepositoryProviderFactory(
        graph
    )
    if fail_second_save:
        provider_factory = _FailingProviderFactory(provider_factory)
    scope_factory = CommandScopeFactory(
        InMemoryUnitOfWorkTransactionFactory(data_store),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=provider_factory,
    )
    service = SpotGraphItemTransferService(
        spot_graph_repository=graph,
        player_inventory_repository=inventories,
        spot_interior_repository=InMemorySpotInteriorRepository(),
        item_repository=items,
        player_status_repository=statuses,
        give_item_command_scope_factory=scope_factory,
    )
    return service, inventories, item.item_instance_id, observations


def test_give_item_commits_both_inventories_before_observation() -> None:
    """正常時は両inventoryを確定してから成功観測を1件だけ配送する。"""
    service, inventories, item_id, observations = _build_scoped_service()

    service.give_item(PLAYER_ID, OTHER_PLAYER_ID, SlotId(0))

    sender = inventories.find_by_id(PLAYER_ID)
    recipient = inventories.find_by_id(OTHER_PLAYER_ID)
    assert sender.get_item_instance_id_by_slot(SlotId(0)) is None
    assert recipient.get_item_instance_id_by_slot(SlotId(0)) == item_id
    assert observations == [_CommitObservation(False, True)]


def test_recipient_save_failure_rolls_back_both_inventories_and_observation() -> None:
    """受け手保存で失敗すると送り手側も戻し、成功観測を配送しない。"""
    service, inventories, item_id, observations = _build_scoped_service(
        fail_second_save=True
    )

    with pytest.raises(RuntimeError, match="recipient save failed"):
        service.give_item(PLAYER_ID, OTHER_PLAYER_ID, SlotId(0))

    sender = inventories.find_by_id(PLAYER_ID)
    recipient = inventories.find_by_id(OTHER_PLAYER_ID)
    assert sender.get_item_instance_id_by_slot(SlotId(0)) == item_id
    assert recipient.get_item_instance_id_by_slot(SlotId(0)) is None
    assert observations == []
