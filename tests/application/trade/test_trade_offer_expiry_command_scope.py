"""期限切れ取引提案のoffer単位確定境界を保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.trade.services.in_memory_pending_trade_offer_store import (
    InMemoryPendingTradeOfferStore,
)
from ai_rpg_world.application.trade.services.trade_freeze_service import (
    TradeFreezeService,
)
from ai_rpg_world.application.trade.services.trade_offer_expiry_stage import (
    TradeOfferExpiryStage,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_offer_expiry_command_repository_provider import (
    InMemoryTradeOfferExpiryCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
    build_trade_offer_expiry_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)


OFFERER = PlayerId(1)
TARGET = PlayerId(2)
SPEC_ID = ItemSpecId(10)


def _item_spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=SPEC_ID,
        name="乾パン",
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON,
        description="取引期限試験用",
        max_stack_size=MaxStackSize(1),
    )


def _offer(
    store: InMemoryPendingTradeOfferStore,
    *,
    offerer: PlayerId = OFFERER,
    target: PlayerId = TARGET,
) -> PendingTradeOffer:
    offer = PendingTradeOffer.create(
        offer_id=store.next_offer_id(),
        offerer_player_id=offerer,
        target_player_id=target,
        gives=TradeSide(items=((SPEC_ID.value, 1),)),
        asks=TradeSide(gold=6),
        created_tick=0,
        expires_in_ticks=1,
    )
    store.put(offer)
    return offer


def _seed_reserved_item(
    store: InMemoryDataStore,
    *,
    player_id: PlayerId,
    item_instance_id: int,
) -> None:
    item_id = ItemInstanceId(item_instance_id)
    item_repository = InMemoryItemRepository(store)
    inventory_repository = InMemoryPlayerInventoryRepository(store)
    item_repository.save(ItemAggregate.create(item_id, _item_spec(), quantity=1))
    inventory = PlayerInventoryAggregate.create_new_inventory(player_id, max_slots=4)
    inventory.acquire_item(item_id, item_spec_id_value=SPEC_ID.value)
    inventory.reserve_item(SlotId(0))
    inventory_repository.save(inventory)


def _stage(
    data_store: InMemoryDataStore,
    offer_store: InMemoryPendingTradeOfferStore,
    *,
    observer=None,
) -> TradeOfferExpiryStage:
    dispatcher = CommandEventDispatcher()
    scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_trade_offer_expiry_rollback_participants(
                pending_trade_offers=offer_store,
            ),
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=(
            InMemoryTradeOfferExpiryCommandRepositoryProviderFactory()
        ),
    )
    # scope中に長寿命repositoryへ戻る退行を検出できるよう、旧repositoryは
    # transaction対象とは別storeへ向ける。
    legacy_store = InMemoryDataStore()
    freeze = TradeFreezeService(
        pending_trade_offer_store=offer_store,
        player_inventory_repository=InMemoryPlayerInventoryRepository(legacy_store),
        player_status_repository=None,
        item_repository=InMemoryItemRepository(legacy_store),
    )
    return TradeOfferExpiryStage(
        pending_trade_offer_store=offer_store,
        trade_freeze_service=freeze,
        expiry_observer=observer,
        command_scope_factory=scope_factory,
    )


def test_observer_sees_offer_removed_and_inventory_unreserved_after_commit() -> None:
    """期限切れ観測は提案削除と予約解除がともに確定した後だけ呼ばれる。"""
    data_store = InMemoryDataStore()
    offer_store = InMemoryPendingTradeOfferStore()
    _seed_reserved_item(data_store, player_id=OFFERER, item_instance_id=100)
    offer = _offer(offer_store)
    observations: list[tuple[bool, frozenset[ItemInstanceId]]] = []
    inventory_repository = InMemoryPlayerInventoryRepository(data_store)

    def observe(expired_offer: PendingTradeOffer) -> None:
        inventory = inventory_repository.find_by_id(expired_offer.offerer_player_id)
        observations.append(
            (
                offer_store.find(expired_offer.offer_id) is None,
                inventory.reserved_item_ids,
            )
        )

    _stage(data_store, offer_store, observer=observe).run(2)

    assert observations == [(True, frozenset())]
    assert offer_store.find(offer.offer_id) is None


def test_offer_store_failure_rolls_back_removal_and_inventory_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """提案削除後の失敗でも、提案とinventory予約を開始前へ戻す。"""
    data_store = InMemoryDataStore()
    offer_store = InMemoryPendingTradeOfferStore()
    item_id = ItemInstanceId(100)
    _seed_reserved_item(data_store, player_id=OFFERER, item_instance_id=item_id.value)
    offer = _offer(offer_store)
    observed: list[int] = []
    original_put = offer_store.put

    def fail_after_put(updated_offer: PendingTradeOffer) -> None:
        original_put(updated_offer)
        if not updated_offer.is_pending:
            raise RuntimeError("offer store failed after removal")

    monkeypatch.setattr(offer_store, "put", fail_after_put)

    with pytest.raises(RuntimeError, match="offer store failed after removal"):
        _stage(data_store, offer_store, observer=lambda value: observed.append(1)).run(2)

    restored = offer_store.find(offer.offer_id)
    inventory = InMemoryPlayerInventoryRepository(data_store).find_by_id(OFFERER)
    assert restored is not None and restored.is_pending
    assert inventory.reserved_item_ids == frozenset({item_id})
    assert observed == []


def test_each_offer_commits_independently_before_a_later_offer_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """先行offerの確定と観測は、後続offerのrollbackで取り消されない。"""
    data_store = InMemoryDataStore()
    offer_store = InMemoryPendingTradeOfferStore()
    second_offerer = PlayerId(3)
    _seed_reserved_item(data_store, player_id=OFFERER, item_instance_id=100)
    _seed_reserved_item(data_store, player_id=second_offerer, item_instance_id=200)
    first = _offer(offer_store)
    second = _offer(
        offer_store,
        offerer=second_offerer,
        target=TARGET,
    )
    original_put = offer_store.put

    def fail_for_second(updated_offer: PendingTradeOffer) -> None:
        original_put(updated_offer)
        if updated_offer.offer_id == second.offer_id and not updated_offer.is_pending:
            raise RuntimeError("second offer failed")

    monkeypatch.setattr(offer_store, "put", fail_for_second)
    observed: list[int] = []

    with pytest.raises(RuntimeError, match="second offer failed"):
        _stage(
            data_store,
            offer_store,
            observer=lambda value: observed.append(value.offer_id.value),
        ).run(2)

    first_inventory = InMemoryPlayerInventoryRepository(data_store).find_by_id(OFFERER)
    second_inventory = InMemoryPlayerInventoryRepository(data_store).find_by_id(
        second_offerer
    )
    assert offer_store.find(first.offer_id) is None
    assert first_inventory.reserved_item_ids == frozenset()
    assert offer_store.find(second.offer_id) is not None
    assert second_inventory.reserved_item_ids == frozenset({ItemInstanceId(200)})
    assert observed == [first.offer_id.value]


def test_post_commit_cleanup_failure_notifies_then_preserves_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit済みcleanup失敗では期限切れを通知し、専用例外を維持する。"""
    data_store = InMemoryDataStore()
    offer_store = InMemoryPendingTradeOfferStore()
    _seed_reserved_item(data_store, player_id=OFFERER, item_instance_id=100)
    offer = _offer(offer_store)
    observed: list[int] = []
    original_release = data_store.release_uow_transaction

    def fail_after_release() -> None:
        original_release()
        raise RuntimeError("trade expiry cleanup failed")

    monkeypatch.setattr(data_store, "release_uow_transaction", fail_after_release)

    with pytest.raises(CommandPostCommitException):
        _stage(
            data_store,
            offer_store,
            observer=lambda value: observed.append(value.offer_id.value),
        ).run(2)

    inventory = InMemoryPlayerInventoryRepository(data_store).find_by_id(OFFERER)
    assert offer_store.find(offer.offer_id) is None
    assert inventory.reserved_item_ids == frozenset()
    assert observed == [offer.offer_id.value]


def test_observer_failure_does_not_undo_committed_expiry() -> None:
    """確定後観測の失敗は、提案削除と予約解除を取り消さない。"""
    data_store = InMemoryDataStore()
    offer_store = InMemoryPendingTradeOfferStore()
    _seed_reserved_item(data_store, player_id=OFFERER, item_instance_id=100)
    offer = _offer(offer_store)

    def fail_observer(_offer: PendingTradeOffer) -> None:
        raise RuntimeError("expiry observation failed")

    _stage(data_store, offer_store, observer=fail_observer).run(2)

    inventory = InMemoryPlayerInventoryRepository(data_store).find_by_id(OFFERER)
    assert offer_store.find(offer.offer_id) is None
    assert inventory.reserved_item_ids == frozenset()
