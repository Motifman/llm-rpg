"""TradeCommandServiceの新しいcommand確定境界を検証する。"""

from __future__ import annotations

import ast
import inspect

import pytest

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.trade.contracts.commands import OfferItemCommand
from ai_rpg_world.application.trade.services.trade_command_service import TradeCommandService
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId

from tests.application.trade.services.test_trade_command_service import (
    _build_in_memory_service,
)


class _RaisingSyncDispatcher:
    def dispatch(self, event: object, context: object) -> None:
        raise RuntimeError("sync failed")


class _RaisingHandoff:
    def handoff(self, events: object) -> None:
        raise RuntimeError("handoff failed")


def _seed_offer_dependencies(setup: tuple[object, ...]) -> OfferItemCommand:
    _, _, inventory_repository, _, _, _, profile_repository, item_repository = setup
    player_id = PlayerId(1)
    item_id = ItemInstanceId(10)
    item_spec = ItemSpec(
        item_spec_id=ItemSpecId(1),
        name="TradeItem",
        item_type=ItemType.CONSUMABLE,
        rarity=Rarity.COMMON,
        description="scope migration test",
        max_stack_size=MaxStackSize(64),
    )
    inventory = PlayerInventoryAggregate.create_new_inventory(player_id, max_slots=10)
    inventory.acquire_item(item_id, item_spec_id_value=item_spec.item_spec_id.value)
    inventory_repository.save(inventory)
    profile_repository.save(
        PlayerProfileAggregate.create(player_id, PlayerName("SellerOne"))
    )
    item_repository.save(ItemAggregate.create(item_id, item_spec, quantity=1))
    return OfferItemCommand(
        seller_id=1,
        slot_id=SlotId(0).value,
        item_instance_id=10,
        requested_gold=50,
        is_direct=False,
    )


def test_sync_dispatch_failure_rolls_back_trade_and_inventory() -> None:
    """同期処理が失敗すると取引作成・採番・所持品予約をすべて破棄する。"""
    setup = _build_in_memory_service(sync_dispatcher=_RaisingSyncDispatcher())
    service, trade_repository, inventory_repository, *_ = setup
    command = _seed_offer_dependencies(setup)

    with pytest.raises(Exception) as caught:
        service.offer_item(command)

    assert "sync failed" in str(caught.value)
    assert trade_repository.find_by_id(TradeId(1)) is None
    inventory = inventory_repository.find_by_id(PlayerId(1))
    assert inventory is not None
    assert inventory.reserved_item_ids == frozenset()


def test_handoff_failure_keeps_committed_trade_and_remains_distinguishable() -> None:
    """commit後の引渡し失敗は専用例外で通知し、確定済み取引を戻さない。"""
    setup = _build_in_memory_service(after_commit_handoff=_RaisingHandoff())
    service, trade_repository, inventory_repository, *_ = setup
    command = _seed_offer_dependencies(setup)

    with pytest.raises(CommandPostCommitException):
        service.offer_item(command)

    assert trade_repository.find_by_id(TradeId(1)) is not None
    inventory = inventory_repository.find_by_id(PlayerId(1))
    assert inventory is not None
    assert inventory.reserved_item_ids == frozenset({ItemInstanceId(10)})


def test_each_trade_command_uses_one_fresh_scope_and_no_legacy_repository_fields() -> None:
    """4コマンドは各1回だけscopeを作り、旧UoW・repositoryフィールドを保持しない。"""
    source = inspect.getsource(TradeCommandService)
    tree = ast.parse(source)
    forbidden = {
        "_unit_of_work",
        "_trade_repository",
        "_player_inventory_repository",
        "_player_status_repository",
        "_player_profile_repository",
        "_item_repository",
    }
    accessed_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert forbidden.isdisjoint(accessed_attributes)

    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for method_name in (
        "_offer_item_impl",
        "_accept_trade_impl",
        "_cancel_trade_impl",
        "_decline_trade_impl",
    ):
        create_calls = [
            node
            for node in ast.walk(methods[method_name])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create"
        ]
        assert len(create_calls) == 1
