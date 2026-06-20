"""SpotGraphItemTransferService の drop / pickup 挙動。

タイルマップ時代の ItemDroppedFromInventoryDropHandler は
``physical_map`` 依存で world_runtime / spot-graph 世界では発火しない。
本サービスは SpotInterior.ground_items に直接書き込む新経路で、その
最小往復 (drop → pickup) と境界条件を保証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    ItemTransferException,
    SpotGraphItemTransferService,
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
from ai_rpg_world.domain.player.exception.player_exceptions import (
    ItemNotInSlotException,
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


def _make_graph_with_player(spot_id: SpotId, player_ids: tuple[PlayerId, ...]) -> SpotGraphAggregate:
    """指定 spot_id にプレイヤーを配置した最小グラフ。"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(
        SpotNode(
            spot_id=spot_id,
            name="テスト地点",
            description="テスト用",
            category=SpotCategoryEnum.FIELD,
            parent_id=None,
        )
    )
    for pid in player_ids:
        graph.place_entity(EntityId.create(int(pid)), spot_id)
    graph.clear_events()
    return graph


def _make_item_spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=ITEM_SPEC_ID,
        name="流木",
        item_type=ItemType.MATERIAL,
        rarity=Rarity.COMMON,
        description="乾いた流木。焚き火に使える。",
        max_stack_size=MaxStackSize(64),
    )


@pytest.fixture
def transfer_service():
    """drop/pickup 経路の最小構築 (player A が SPOT_ID にいて流木を 1 個所持)。"""
    spot_graph_repo = InMemorySpotGraphRepository(
        _make_graph_with_player(SPOT_ID, (PLAYER_ID,))
    )
    inventory_repo = InMemoryPlayerInventoryRepository()
    spot_interior_repo = InMemorySpotInteriorRepository()
    item_repo = InMemoryItemRepository()

    inventory = PlayerInventoryAggregate.create_new_inventory(PLAYER_ID)
    item_spec = _make_item_spec()
    instance_id = item_repo.generate_item_instance_id()
    item_repo.save(
        ItemAggregate.create(
            item_instance_id=instance_id,
            item_spec=item_spec,
            quantity=1,
        )
    )
    inventory.acquire_item(instance_id, item_spec_id_value=item_spec.item_spec_id.value)
    inventory_repo.save(inventory)
    spot_interior_repo.save(SPOT_ID, SpotInterior.empty())

    service = SpotGraphItemTransferService(
        spot_graph_repository=spot_graph_repo,
        player_inventory_repository=inventory_repo,
        spot_interior_repository=spot_interior_repo,
        item_repository=item_repo,
    )
    return {
        "service": service,
        "spot_graph_repo": spot_graph_repo,
        "inventory_repo": inventory_repo,
        "spot_interior_repo": spot_interior_repo,
        "item_repo": item_repo,
        "instance_id": instance_id,
    }


class TestSpotGraphItemTransferServiceDrop:
    """drop が SpotInterior.ground_items に書き込む経路を保証する。"""

    def test_drop_する_と_インベントリから消えて地面に出現する(self, transfer_service):
        """drop_item 後、インベントリは空 / 地面に GroundItem が 1 つ。"""
        deps = transfer_service
        result = deps["service"].drop_item(PLAYER_ID, SlotId(0))

        inv = deps["inventory_repo"].find_by_id(PLAYER_ID)
        assert inv.get_item_instance_id_by_slot(SlotId(0)) is None

        interior = deps["spot_interior_repo"].find_by_spot_id(SPOT_ID)
        assert len(interior.ground_items) == 1
        assert interior.ground_items[0].item_instance_id == deps["instance_id"]
        assert interior.ground_items[0].item_spec_id == ITEM_SPEC_ID

        assert result.item_instance_id == deps["instance_id"]
        assert result.spot_id == SPOT_ID
        assert any("流木" in m for m in result.messages)

    def test_drop_は空のスロットでは_ItemNotInSlotException_を投げる(self, transfer_service):
        """空スロットを drop しようとするとドメイン例外。"""
        deps = transfer_service
        with pytest.raises(ItemNotInSlotException):
            deps["service"].drop_item(PLAYER_ID, SlotId(5))  # 5 番スロットは空

    def test_drop_はグラフに居ないプレイヤーで_ItemTransferException_を投げる(self, transfer_service):
        """SpotGraphAggregate に place_entity されてないプレイヤーで drop すると境界例外。

        orphan のインベントリにもアイテムを 1 つ入れておくことで、
        ItemNotInSlot ではなく spot 解決失敗で例外が出ることを保証する。
        """
        deps = transfer_service
        orphan_inv = PlayerInventoryAggregate.create_new_inventory(OTHER_PLAYER_ID)
        orphan_iid = deps["item_repo"].generate_item_instance_id()
        deps["item_repo"].save(
            ItemAggregate.create(
                item_instance_id=orphan_iid,
                item_spec=_make_item_spec(),
                quantity=1,
            )
        )
        orphan_inv.acquire_item(
            orphan_iid, item_spec_id_value=ITEM_SPEC_ID.value
        )
        deps["inventory_repo"].save(orphan_inv)
        # OTHER_PLAYER_ID は spot_graph に place_entity されていない
        with pytest.raises(ItemTransferException):
            deps["service"].drop_item(OTHER_PLAYER_ID, SlotId(0))


class TestSpotGraphItemTransferServicePickup:
    """pickup が SpotInterior.ground_items から拾い上げてインベントリに入れる経路を保証する。"""

    def test_drop_の直後に_pickup_すると_往復で元に戻る(self, transfer_service):
        """drop → pickup の最短往復で player のインベントリに戻る。"""
        deps = transfer_service
        deps["service"].drop_item(PLAYER_ID, SlotId(0))
        deps["service"].pickup_item(PLAYER_ID, deps["instance_id"])

        inv = deps["inventory_repo"].find_by_id(PLAYER_ID)
        assert inv.get_item_instance_id_by_slot(SlotId(0)) == deps["instance_id"]

        interior = deps["spot_interior_repo"].find_by_spot_id(SPOT_ID)
        assert interior.ground_items == ()

    def test_他人が_drop_したアイテムを別プレイヤーが拾える(self, transfer_service):
        """これが本 PR の本質: A が落として B が拾う、を機械的に通す。"""
        deps = transfer_service
        # B もスポットに配置: 既存グラフに place_entity を追加する
        graph = deps["spot_graph_repo"].find_graph()
        graph.place_entity(EntityId.create(int(OTHER_PLAYER_ID)), SPOT_ID)
        graph.clear_events()
        deps["spot_graph_repo"].save(graph)
        b_inventory = PlayerInventoryAggregate.create_new_inventory(OTHER_PLAYER_ID)
        deps["inventory_repo"].save(b_inventory)

        deps["service"].drop_item(PLAYER_ID, SlotId(0))
        deps["service"].pickup_item(OTHER_PLAYER_ID, deps["instance_id"])

        a_inv = deps["inventory_repo"].find_by_id(PLAYER_ID)
        b_inv = deps["inventory_repo"].find_by_id(OTHER_PLAYER_ID)
        assert a_inv.get_item_instance_id_by_slot(SlotId(0)) is None
        assert b_inv.get_item_instance_id_by_slot(SlotId(0)) == deps["instance_id"]

    def test_pickup_は地面にないアイテムで_ItemTransferException_を投げる(self, transfer_service):
        """ground_items に無い instance_id を拾おうとすると境界例外。"""
        deps = transfer_service
        nowhere = ItemInstanceId.create(999)
        with pytest.raises(ItemTransferException):
            deps["service"].pickup_item(PLAYER_ID, nowhere)

    def test_list_ground_items_at_player_spot_は現在地の地面一覧を返す(self, transfer_service):
        """ランナー/将来の LLM tool が「拾える物」を列挙するヘルパ。"""
        deps = transfer_service
        assert deps["service"].list_ground_items_at_player_spot(PLAYER_ID) == ()
        deps["service"].drop_item(PLAYER_ID, SlotId(0))
        items = deps["service"].list_ground_items_at_player_spot(PLAYER_ID)
        assert len(items) == 1
        assert items[0].item_instance_id == deps["instance_id"]


class TestSpotGraphItemTransferServiceIdempotency:
    """drop の二重実行と pickup の二重実行が geometry を壊さない。"""

    def test_with_ground_item_は_idempotent_なので_二重_drop_でも壊れない(self, transfer_service):
        """drop した instance を再度 SpotInterior に追加しても重複しない。"""
        deps = transfer_service
        deps["service"].drop_item(PLAYER_ID, SlotId(0))
        interior = deps["spot_interior_repo"].find_by_spot_id(SPOT_ID)
        # 直接 with_ground_item を二度呼んでも 1 個のまま (idempotency 仕様)
        interior2 = interior.with_ground_item(interior.ground_items[0])
        assert len(interior2.ground_items) == 1


class TestSpotGraphItemTransferServiceGive:
    """give_item: 同室の別プレイヤーへの直接受渡し。"""

    def _add_other_player_to_spot(self, deps, player_id: PlayerId) -> None:
        """B のインベントリと spot 配置を整える (テスト fixture が A のみ用なため)。"""
        graph = deps["spot_graph_repo"].find_graph()
        graph.place_entity(EntityId.create(int(player_id)), SPOT_ID)
        graph.clear_events()
        deps["spot_graph_repo"].save(graph)
        b_inv = PlayerInventoryAggregate.create_new_inventory(player_id)
        deps["inventory_repo"].save(b_inv)

    def test_同室の別プレイヤーへ渡せる(self, transfer_service):
        """A の slot 0 アイテムが B の任意の slot へ移る。"""
        deps = transfer_service
        self._add_other_player_to_spot(deps, OTHER_PLAYER_ID)

        result = deps["service"].give_item(PLAYER_ID, OTHER_PLAYER_ID, SlotId(0))

        a_inv = deps["inventory_repo"].find_by_id(PLAYER_ID)
        b_inv = deps["inventory_repo"].find_by_id(OTHER_PLAYER_ID)
        assert a_inv.get_item_instance_id_by_slot(SlotId(0)) is None
        assert b_inv.get_item_instance_id_by_slot(SlotId(0)) == deps["instance_id"]
        assert result.item_instance_id == deps["instance_id"]
        assert any("流木" in m for m in result.messages)

    def test_自分自身に渡そうとすると_ItemTransferException(self, transfer_service):
        """A → A は弾く。"""
        deps = transfer_service
        with pytest.raises(ItemTransferException):
            deps["service"].give_item(PLAYER_ID, PLAYER_ID, SlotId(0))

    def test_別スポットの相手には渡せない(self, transfer_service):
        """B が別 spot に居る場合は弾く。"""
        deps = transfer_service
        # B を別の spot に配置する
        other_spot = SpotId.create(99)
        graph = deps["spot_graph_repo"].find_graph()
        graph.add_spot(
            SpotNode(
                spot_id=other_spot,
                name="別地点",
                description="",
                category=SpotCategoryEnum.FIELD,
                parent_id=None,
            )
        )
        graph.place_entity(EntityId.create(int(OTHER_PLAYER_ID)), other_spot)
        graph.clear_events()
        deps["spot_graph_repo"].save(graph)
        b_inv = PlayerInventoryAggregate.create_new_inventory(OTHER_PLAYER_ID)
        deps["inventory_repo"].save(b_inv)

        with pytest.raises(ItemTransferException):
            deps["service"].give_item(PLAYER_ID, OTHER_PLAYER_ID, SlotId(0))

    def test_空スロットを渡そうとすると_ItemNotInSlotException(self, transfer_service):
        """A のスロット 5 は空。"""
        deps = transfer_service
        self._add_other_player_to_spot(deps, OTHER_PLAYER_ID)
        with pytest.raises(ItemNotInSlotException):
            deps["service"].give_item(PLAYER_ID, OTHER_PLAYER_ID, SlotId(5))

    def test_受け手のインベントリ満杯時は弾かれ送り手側にアイテムが残る(self, transfer_service):
        """orphan item silent failure 回帰: 受け手満杯なら ItemTransferException を投げ、
        送り手から抜かない & item_repository 上の instance は残る。

        以前は send 側を先に抜いてから to_inv.acquire_item を呼んでいたため、
        満杯時は overflow event だけが発火し、instance が両者のスロットから
        消えて item_repository だけに残る orphan 状態が出る silent failure だった。
        """
        deps = transfer_service
        self._add_other_player_to_spot(deps, OTHER_PLAYER_ID)

        # 受け手 B のインベントリを満杯にする
        b_inv = deps["inventory_repo"].find_by_id(OTHER_PLAYER_ID)
        for i in range(b_inv._max_slots):
            filler_id = deps["item_repo"].generate_item_instance_id()
            deps["item_repo"].save(
                ItemAggregate.create(
                    item_instance_id=filler_id,
                    item_spec=_make_item_spec(),
                    quantity=1,
                )
            )
            b_inv.acquire_item(filler_id, item_spec_id_value=ITEM_SPEC_ID.value)
        deps["inventory_repo"].save(b_inv)
        assert b_inv.is_inventory_full()

        with pytest.raises(ItemTransferException):
            deps["service"].give_item(PLAYER_ID, OTHER_PLAYER_ID, SlotId(0))

        # 送り手 A はアイテムを失っていない
        a_inv = deps["inventory_repo"].find_by_id(PLAYER_ID)
        assert a_inv.get_item_instance_id_by_slot(SlotId(0)) == deps["instance_id"]
        # instance も item_repository に残っている (orphan ではない)
        assert deps["item_repo"].find_by_id(deps["instance_id"]) is not None
