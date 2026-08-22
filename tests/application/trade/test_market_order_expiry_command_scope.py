"""市場注文期限切れの注文単位確定境界を保証する。"""

from pathlib import Path
from typing import Any

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.trade.services.market_service import MarketService
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.market_board import MarketBoard

_SCENARIO = Path("data/scenarios/market_town_v3_board.json")
_PLAYER = PlayerId(1)
_HERB = "薬草"
_BREAD = "焼きたてのパン"


def _runtime() -> Any:
    return create_world_runtime(_SCENARIO)


def _spec_id(runtime: Any, label: str) -> int:
    return runtime._item_spec_repo.find_by_name(label).item_spec_id.value


def _give(runtime: Any, label: str, count: int = 1) -> None:
    grant_item_specs_to_inventory(
        _PLAYER,
        tuple(ItemSpecId.create(_spec_id(runtime, label)) for _ in range(count)),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _held(runtime: Any, label: str) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(_PLAYER)
    counts = count_owned_item_instances_by_spec(inventory, runtime._item_repo)
    spec_id = _spec_id(runtime, label)
    return sum(count for spec, count in counts.items() if spec.value == spec_id)


def _gold(runtime: Any) -> int:
    return runtime._player_status_repo.find_by_id(_PLAYER).gold.value


def _stage(runtime: Any):  # noqa: ANN202
    return runtime._simulation_service._market_order_expiry_stage


class _ForbiddenRepository:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"legacy repository must not be used: {name}")


class _CommitObservation:
    def __init__(self, runtime: Any, order_id: Any) -> None:
        self._runtime = runtime
        self._order_id = order_id
        self.states: list[tuple[bool, int]] = []

    def publish_all(self, events: Any) -> None:
        assert tuple(events)
        self.states.append(
            (
                self._runtime._market_board_store.board().find(self._order_id)
                is None,
                _held(self._runtime, _HERB),
            )
        )


class _BrokenObservation:
    def publish_all(self, events: Any) -> None:
        assert tuple(events)
        raise RuntimeError("expiry observation failed")


def test_sell_expiry_observation_sees_committed_board_and_inventory() -> None:
    """売り注文の観測時点では、板の削除と品の返却がともに確定している。"""
    runtime = _runtime()
    market: MarketService = runtime._market_service
    _give(runtime, _HERB)
    order = market.place_sell_order(
        _PLAYER,
        item_label=_HERB,
        quantity=1,
        unit_price=8,
        current_tick=1,
    )
    observer = _CommitObservation(runtime, order.order_id)
    market.set_event_publisher(observer)
    market._inventories = _ForbiddenRepository()
    market._statuses = _ForbiddenRepository()
    market._items = _ForbiddenRepository()

    _stage(runtime).run(WorldTick(order.expires_at_tick + 1))

    assert observer.states == [(True, 1)]
    assert runtime._market_board_store.board().find(order.order_id) is None


def test_sell_expiry_save_failure_rolls_back_goods_and_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """品を返した後の板保存失敗では、品も板も開始前へ戻る。"""
    runtime = _runtime()
    market: MarketService = runtime._market_service
    _give(runtime, _HERB)
    order = market.place_sell_order(
        _PLAYER,
        item_label=_HERB,
        quantity=1,
        unit_price=8,
        current_tick=1,
    )
    store = runtime._market_board_store
    original_save = store.save

    def save_then_fail(board: Any) -> None:
        original_save(board)
        if board.find(order.order_id) is None:
            raise RuntimeError("board save failed")

    monkeypatch.setattr(store, "save", save_then_fail)

    _stage(runtime).run(WorldTick(order.expires_at_tick + 1))

    assert store.board().find(order.order_id) == order
    assert _held(runtime, _HERB) == 0


def test_buy_expiry_save_failure_rolls_back_gold_and_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """goldを返した後の板保存失敗では、残高も板も開始前へ戻る。"""
    runtime = _runtime()
    market: MarketService = runtime._market_service
    before = _gold(runtime)
    order = market.place_buy_order(
        _PLAYER,
        item_label=_HERB,
        quantity=1,
        unit_price=2,
        current_tick=1,
    )
    deposited = _gold(runtime)
    store = runtime._market_board_store
    original_save = store.save

    def save_then_fail(board: Any) -> None:
        original_save(board)
        if board.find(order.order_id) is None:
            raise RuntimeError("board save failed")

    monkeypatch.setattr(store, "save", save_then_fail)

    _stage(runtime).run(WorldTick(order.expires_at_tick + 1))

    assert deposited == before - order.total_gold
    assert store.board().find(order.order_id) == order
    assert _gold(runtime) == deposited


def test_failed_order_does_not_stop_later_independent_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """先行注文がrollbackしても、後続注文は独立して返却・削除できる。"""
    runtime = _runtime()
    market: MarketService = runtime._market_service
    _give(runtime, _HERB)
    sell = market.place_sell_order(
        _PLAYER,
        item_label=_HERB,
        quantity=1,
        unit_price=8,
        current_tick=1,
    )
    gold_after_sell = _gold(runtime)
    buy = market.place_buy_order(
        _PLAYER,
        item_label=_BREAD,
        quantity=1,
        unit_price=2,
        current_tick=1,
    )
    gold_after_deposit = _gold(runtime)
    store = runtime._market_board_store
    original_save = store.save

    def fail_only_sell(board: Any) -> None:
        original_save(board)
        if board.find(sell.order_id) is None and board.find(buy.order_id) is not None:
            raise RuntimeError("sell expiry failed")

    monkeypatch.setattr(store, "save", fail_only_sell)

    _stage(runtime).run(WorldTick(sell.expires_at_tick + 1))

    assert store.board().find(sell.order_id) == sell
    assert store.board().find(buy.order_id) is None
    assert _held(runtime, _HERB) == 0
    assert gold_after_deposit == gold_after_sell - buy.total_gold
    assert _gold(runtime) == gold_after_sell


def test_full_inventory_commits_awaiting_collection_without_losing_goods() -> None:
    """返却不能な売り注文は、品を増減せず引き取り待ちとして確定する。"""
    runtime = _runtime()
    market: MarketService = runtime._market_service
    _give(runtime, _HERB)
    order = market.place_sell_order(
        _PLAYER,
        item_label=_HERB,
        quantity=1,
        unit_price=8,
        current_tick=1,
    )
    inventory = runtime._player_inventory_repo.find_by_id(_PLAYER)
    while not inventory.is_inventory_full():
        _give(runtime, _BREAD)
        inventory = runtime._player_inventory_repo.find_by_id(_PLAYER)

    _stage(runtime).run(WorldTick(order.expires_at_tick + 1))

    waiting = runtime._market_board_store.board().find(order.order_id)
    assert waiting is not None
    assert waiting.is_awaiting_collection is True
    assert _held(runtime, _HERB) == 0


def test_post_commit_cleanup_failure_notifies_then_preserves_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit済みcleanup失敗では観測後に専用例外を呼び出し元へ返す。"""
    runtime = _runtime()
    market: MarketService = runtime._market_service
    runtime._market_board_store.save(MarketBoard.empty())
    _give(runtime, _HERB)
    order = market.place_sell_order(
        _PLAYER,
        item_label=_HERB,
        quantity=1,
        unit_price=8,
        current_tick=1,
    )
    observer = _CommitObservation(runtime, order.order_id)
    market.set_event_publisher(observer)
    data_store = runtime._item_repo._data_store
    original_release = data_store.release_uow_transaction

    def release_then_fail() -> None:
        original_release()
        raise RuntimeError("market expiry cleanup failed")

    monkeypatch.setattr(data_store, "release_uow_transaction", release_then_fail)

    with pytest.raises(CommandPostCommitException):
        _stage(runtime).run(WorldTick(order.expires_at_tick + 1))

    assert runtime._market_board_store.board().find(order.order_id) is None
    assert _held(runtime, _HERB) == 1
    assert observer.states == [(True, 1)]


def test_observation_failure_does_not_undo_committed_expiry() -> None:
    """確定後観測の失敗は、板の削除と返却を取り消さない。"""
    runtime = _runtime()
    market: MarketService = runtime._market_service
    _give(runtime, _HERB)
    order = market.place_sell_order(
        _PLAYER,
        item_label=_HERB,
        quantity=1,
        unit_price=8,
        current_tick=1,
    )
    market.set_event_publisher(_BrokenObservation())

    _stage(runtime).run(WorldTick(order.expires_at_tick + 1))

    assert runtime._market_board_store.board().find(order.order_id) is None
    assert _held(runtime, _HERB) == 1
