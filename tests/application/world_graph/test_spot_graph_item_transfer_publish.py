"""SpotGraphItemTransferService の publisher 配信挙動を固定する特性化テスト。

ドメインイベント配信一元化リファクタ Stage 2。item_transfer を「その場 publish」から
「collector で収集 → オペレーション境界で 1 度 dispatch」へ移行する際に、外から見える
配信挙動が変わらないことを保証する:

- drop → PlayerDroppedItemEvent / pickup → PlayerPickedUpItemEvent /
  give → PlayerGaveItemEvent がそれぞれ 1 件ずつ publish される。
- publisher 未注入 (None) なら発火せず状態遷移のみ (最小構成の後方互換)。
- publisher が例外を投げても本体オペレーションは成功する (相② best-effort)。

既存 test_spot_graph_item_transfer_service.py は publisher 未注入経路のみを見ており、
publisher 注入時の配信集合を固定するテストが無かったため本ファイルで補う。
"""

from __future__ import annotations

from typing import List

import pytest

from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    SpotGraphItemTransferService,
)
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerDroppedItemEvent,
    PlayerGaveItemEvent,
    PlayerPickedUpItemEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
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


PLAYER_ID = PlayerId(1)
OTHER_PLAYER_ID = PlayerId(2)
SPOT_ID = SpotId.create(10)
ITEM_SPEC_ID = ItemSpecId.create(100)


class _SpyPublisher:
    """publish_all で受け取ったイベントを平坦に記録する duck-typed publisher。"""

    def __init__(self) -> None:
        self.published: List[object] = []

    def publish_all(self, events) -> None:
        self.published.extend(events)


class _RaisingPublisher:
    """publish_all が必ず例外を投げる publisher (best-effort ガード検証用)。"""

    def publish_all(self, events) -> None:
        raise RuntimeError("publisher down")


def _make_item_spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=ITEM_SPEC_ID,
        name="流木",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="乾いた流木。",
        max_stack_size=MaxStackSize(64),
    )


def _make_graph(player_ids: tuple[PlayerId, ...]) -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(
        SpotNode(
            spot_id=SPOT_ID,
            name="テスト地点",
            description="テスト用",
            category=SpotCategoryEnum.FIELD,
            parent_id=None,
        )
    )
    for pid in player_ids:
        graph.place_entity(EntityId.create(int(pid)), SPOT_ID)
    graph.clear_events()
    return graph


def _build_service(publisher, *, players: tuple[PlayerId, ...] = (PLAYER_ID,)):
    """流木 1 個を PLAYER_ID が所持した最小構成のサービスを組む。"""
    spot_graph_repo = InMemorySpotGraphRepository(_make_graph(players))
    inventory_repo = InMemoryPlayerInventoryRepository()
    spot_interior_repo = InMemorySpotInteriorRepository()
    item_repo = InMemoryItemRepository()

    item_spec = _make_item_spec()
    instance_id = item_repo.generate_item_instance_id()
    item_repo.save(
        ItemAggregate.create(
            item_instance_id=instance_id, item_spec=item_spec, quantity=1
        )
    )
    inventory = PlayerInventoryAggregate.create_new_inventory(PLAYER_ID)
    inventory.acquire_item(instance_id, item_spec_id_value=item_spec.item_spec_id.value)
    inventory_repo.save(inventory)
    for pid in players:
        if pid != PLAYER_ID:
            inventory_repo.save(PlayerInventoryAggregate.create_new_inventory(pid))
    spot_interior_repo.save(SPOT_ID, SpotInterior.empty())

    service = SpotGraphItemTransferService(
        spot_graph_repository=spot_graph_repo,
        player_inventory_repository=inventory_repo,
        spot_interior_repository=spot_interior_repo,
        item_repository=item_repo,
        event_publisher=publisher,
    )
    return service, instance_id


class TestPublishedEventSet:
    """各オペレーションが期待するイベントを 1 件だけ publish する。"""

    def test_drop_publishes_single_dropped_event(self) -> None:
        """drop_item は PlayerDroppedItemEvent を 1 件 publish する。"""
        spy = _SpyPublisher()
        service, _ = _build_service(spy)

        service.drop_item(PLAYER_ID, SlotId(0))

        assert len(spy.published) == 1
        assert isinstance(spy.published[0], PlayerDroppedItemEvent)

    def test_pickup_publishes_single_picked_up_event(self) -> None:
        """pickup_item は PlayerPickedUpItemEvent を 1 件 publish する。"""
        spy = _SpyPublisher()
        service, instance_id = _build_service(spy)
        service.drop_item(PLAYER_ID, SlotId(0))
        spy.published.clear()

        service.pickup_item(PLAYER_ID, instance_id)

        assert len(spy.published) == 1
        assert isinstance(spy.published[0], PlayerPickedUpItemEvent)

    def test_give_publishes_single_gave_event(self) -> None:
        """give_item は PlayerGaveItemEvent を 1 件 publish する。"""
        spy = _SpyPublisher()
        service, _ = _build_service(spy, players=(PLAYER_ID, OTHER_PLAYER_ID))

        service.give_item(PLAYER_ID, OTHER_PLAYER_ID, SlotId(0))

        assert len(spy.published) == 1
        assert isinstance(spy.published[0], PlayerGaveItemEvent)


class TestPublisherGuards:
    """publisher 未注入・publisher 例外時の挙動を固定する。"""

    def test_no_publisher_still_transfers(self) -> None:
        """publisher=None でも状態遷移は成功する (発火なし)。"""
        service, _ = _build_service(None)

        result = service.drop_item(PLAYER_ID, SlotId(0))

        assert result.spot_id == SPOT_ID

    def test_publisher_exception_is_swallowed(self) -> None:
        """publisher が例外を投げても本体オペレーションは成功する (相② best-effort)。"""
        service, _ = _build_service(_RaisingPublisher())

        result = service.drop_item(PLAYER_ID, SlotId(0))

        assert result.spot_id == SPOT_ID
