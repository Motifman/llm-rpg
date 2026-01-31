import pytest
from typing import Dict, Optional
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.enum.inventory_sort_type import InventorySortType
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    ItemEquipRequestedEvent,
    InventorySlotOverflowEvent,
    InventoryCompactionRequestedEvent,
    InventoryCompactionCompletedEvent,
    InventorySortRequestedEvent
)
from ai_rpg_world.domain.player.exception.player_exceptions import (
    InvalidSlotException,
    ItemNotInSlotException,
    EquipmentSlotValidationException
)


# テスト用のヘルパー関数
def create_test_item_instance_id(value: int = 1) -> ItemInstanceId:
    """テスト用のItemInstanceIdを作成"""
    return ItemInstanceId(value)


def create_test_player_id(value: int = 1) -> PlayerId:
    """テスト用のPlayerIdを作成"""
    return PlayerId(value)


def create_test_slot_id(value: int = 0) -> SlotId:
    """テスト用のSlotIdを作成"""
    return SlotId(value)


def create_test_inventory_slots(
    max_slots: int = 20,
    occupied_slots: Optional[Dict[int, int]] = None
) -> Dict[SlotId, Optional[ItemInstanceId]]:
    """テスト用のインベントリスロットを作成"""
    slots = {}
    for i in range(max_slots):
        slots[SlotId(i)] = None

    if occupied_slots:
        for slot_idx, item_id in occupied_slots.items():
            slots[SlotId(slot_idx)] = ItemInstanceId(item_id)

    return slots


def create_test_equipment_slots(
    occupied_slots: Optional[Dict[EquipmentSlotType, int]] = None
) -> Dict[EquipmentSlotType, Optional[ItemInstanceId]]:
    """テスト用の装備スロットを作成"""
    slots = {}
    for equipment_type in EquipmentSlotType:
        slots[equipment_type] = None

    if occupied_slots:
        for equipment_type, item_id in occupied_slots.items():
            slots[equipment_type] = ItemInstanceId(item_id)

    return slots


def create_test_inventory_aggregate(
    player_id: int = 1,
    max_slots: int = 20,
    inventory_slots: Optional[Dict[int, int]] = None,
    equipment_slots: Optional[Dict[EquipmentSlotType, int]] = None
) -> PlayerInventoryAggregate:
    """テスト用のPlayerInventoryAggregateを作成"""
    inventory_slot_dict = create_test_inventory_slots(max_slots, inventory_slots)
    equipment_slot_dict = create_test_equipment_slots(equipment_slots)

    return PlayerInventoryAggregate.restore_from_data(
        player_id=PlayerId(player_id),
        max_slots=max_slots,
        inventory_slots=inventory_slot_dict,
        equipment_slots=equipment_slot_dict
    )


class TestPlayerInventoryAggregate:
    """PlayerInventoryAggregateのテスト"""

    def test_create_new_inventory(self):
        """新しいインベントリが正しく作成されること"""
        player_id = create_test_player_id(1)
        max_slots = 20

        aggregate = PlayerInventoryAggregate.create_new_inventory(
            player_id=player_id,
            max_slots=max_slots
        )

        assert aggregate.player_id == player_id
        assert aggregate.max_slots == max_slots

        # インベントリスロットが初期化されていることを確認
        for i in range(max_slots):
            slot_id = SlotId(i)
            assert aggregate.get_item_instance_id_by_slot(slot_id) is None

        # 装備スロットが初期化されていることを確認
        for equipment_type in EquipmentSlotType:
            assert aggregate.get_item_instance_id_by_equipment_slot(equipment_type) is None

        # イベントが発行されていないことを確認
        events = aggregate.get_events()
        assert len(events) == 0

    def test_restore_from_data(self):
        """既存データからインベントリが正しく復元されること"""
        player_id = create_test_player_id(1)
        max_slots = 20

        # テストデータを作成
        inventory_slots = create_test_inventory_slots(
            max_slots,
            {0: 100, 5: 200}  # slot 0にitem 100, slot 5にitem 200
        )
        equipment_slots = create_test_equipment_slots(
            {EquipmentSlotType.WEAPON: 300, EquipmentSlotType.ARMOR: 400}
        )

        aggregate = PlayerInventoryAggregate.restore_from_data(
            player_id=player_id,
            max_slots=max_slots,
            inventory_slots=inventory_slots,
            equipment_slots=equipment_slots
        )

        assert aggregate.player_id == player_id
        assert aggregate.max_slots == max_slots

        # インベントリスロットの内容を確認
        assert aggregate.get_item_instance_id_by_slot(SlotId(0)) == ItemInstanceId(100)
        assert aggregate.get_item_instance_id_by_slot(SlotId(5)) == ItemInstanceId(200)
        assert aggregate.get_item_instance_id_by_slot(SlotId(1)) is None  # 空きスロット

        # 装備スロットの内容を確認
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.WEAPON) == ItemInstanceId(300)
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.ARMOR) == ItemInstanceId(400)
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.HELMET) is None

        # イベントが発行されていないことを確認
        events = aggregate.get_events()
        assert len(events) == 0

    def test_restore_from_data_invalid_inventory_slots(self):
        """無効なインベントリスロットデータで復元しようとすると例外が発生すること"""
        player_id = create_test_player_id(1)
        max_slots = 10

        # max_slotsを超えるスロットIDを持つデータを用意
        inventory_slots = {SlotId(i): None for i in range(15)}  # 0-14の15スロット
        equipment_slots = create_test_equipment_slots()

        with pytest.raises(InvalidSlotException):
            PlayerInventoryAggregate.restore_from_data(
                player_id=player_id,
                max_slots=max_slots,
                inventory_slots=inventory_slots,
                equipment_slots=equipment_slots
            )

    def test_restore_from_data_invalid_equipment_slots(self):
        """無効な装備スロットデータで復元しようとすると例外が発生すること"""
        player_id = create_test_player_id(1)
        max_slots = 20

        inventory_slots = create_test_inventory_slots(max_slots)
        # EquipmentSlotTypeの種類が足りないデータを用意
        equipment_slots = {
            EquipmentSlotType.WEAPON: None,
            EquipmentSlotType.HELMET: None,
            # ARMOR, SHIELD, BOOTS, ACCESSORY が欠けている
        }

        with pytest.raises(EquipmentSlotValidationException):
            PlayerInventoryAggregate.restore_from_data(
                player_id=player_id,
                max_slots=max_slots,
                inventory_slots=inventory_slots,
                equipment_slots=equipment_slots
            )

    def test_get_item_instance_id_by_slot_normal(self):
        """スロットからアイテムIDを正しく取得できること"""
        aggregate = create_test_inventory_aggregate(
            inventory_slots={0: 100, 5: 200}
        )

        assert aggregate.get_item_instance_id_by_slot(SlotId(0)) == ItemInstanceId(100)
        assert aggregate.get_item_instance_id_by_slot(SlotId(5)) == ItemInstanceId(200)
        assert aggregate.get_item_instance_id_by_slot(SlotId(1)) is None

    def test_get_item_instance_id_by_slot_invalid_slot(self):
        """無効なスロットIDで取得しようとすると例外が発生すること"""
        aggregate = create_test_inventory_aggregate(max_slots=10)

        with pytest.raises(InvalidSlotException):
            aggregate.get_item_instance_id_by_slot(SlotId(15))  # max_slotsを超える

    def test_get_item_instance_id_by_equipment_slot(self):
        """装備スロットからアイテムIDを正しく取得できること"""
        aggregate = create_test_inventory_aggregate(
            equipment_slots={
                EquipmentSlotType.WEAPON: 100,
                EquipmentSlotType.ARMOR: 200
            }
        )

        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.WEAPON) == ItemInstanceId(100)
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.ARMOR) == ItemInstanceId(200)
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.HELMET) is None

    def test_acquire_item_normal(self):
        """アイテムを正常に入手できること"""
        aggregate = create_test_inventory_aggregate(max_slots=5)
        item_id = create_test_item_instance_id(100)

        aggregate.acquire_item(item_id)

        # 最初の空きスロット（slot 0）にアイテムが配置されていることを確認
        assert aggregate.get_item_instance_id_by_slot(SlotId(0)) == item_id

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], ItemAddedToInventoryEvent)
        assert events[0].aggregate_id == aggregate.player_id
        assert events[0].item_instance_id == item_id

    def test_acquire_item_inventory_full(self):
        """インベントリが満杯の場合、オーバーフローイベントが発行されること"""
        # 全てのスロットを埋めたインベントリを作成
        occupied_slots = {i: 100 + i for i in range(5)}
        aggregate = create_test_inventory_aggregate(
            max_slots=5,
            inventory_slots=occupied_slots
        )
        item_id = create_test_item_instance_id(200)

        # 例外が発生せず処理が完了すること
        aggregate.acquire_item(item_id)

        # オーバーフローイベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], InventorySlotOverflowEvent)
        assert events[0].aggregate_id == aggregate.player_id
        assert events[0].overflowed_item_instance_id == item_id
        assert events[0].reason == "inventory_full_on_acquire"

    def test_move_item_normal(self):
        """アイテムを正常に移動できること"""
        aggregate = create_test_inventory_aggregate(
            max_slots=5,
            inventory_slots={0: 100, 2: 200}
        )

        # slot 0のアイテムをslot 3に移動
        aggregate.move_item(SlotId(0), SlotId(3))

        # 移動結果を確認
        assert aggregate.get_item_instance_id_by_slot(SlotId(0)) is None
        assert aggregate.get_item_instance_id_by_slot(SlotId(3)) == ItemInstanceId(100)
        assert aggregate.get_item_instance_id_by_slot(SlotId(2)) == ItemInstanceId(200)

        # イベントが発行されていないことを確認（移動はイベントを発行しない）
        events = aggregate.get_events()
        assert len(events) == 0

    def test_move_item_same_slot(self):
        """同じスロットへの移動で例外が発生すること"""
        aggregate = create_test_inventory_aggregate(
            inventory_slots={0: 100}
        )

        with pytest.raises(InvalidSlotException):
            aggregate.move_item(SlotId(0), SlotId(0))

    def test_move_item_from_empty_slot(self):
        """空のスロットからの移動で例外が発生すること"""
        aggregate = create_test_inventory_aggregate(max_slots=5)

        with pytest.raises(ItemNotInSlotException):
            aggregate.move_item(SlotId(0), SlotId(1))

    def test_move_item_to_occupied_slot(self):
        """占有されているスロットへの移動で例外が発生すること"""
        aggregate = create_test_inventory_aggregate(
            inventory_slots={0: 100, 1: 200}
        )

        with pytest.raises(InvalidSlotException):
            aggregate.move_item(SlotId(0), SlotId(1))

    def test_drop_item_normal(self):
        """アイテムを正常に捨てられること"""
        aggregate = create_test_inventory_aggregate(
            inventory_slots={0: 100, 2: 200}
        )

        aggregate.drop_item(SlotId(0))

        # アイテムが削除されていることを確認
        assert aggregate.get_item_instance_id_by_slot(SlotId(0)) is None
        assert aggregate.get_item_instance_id_by_slot(SlotId(2)) == ItemInstanceId(200)

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], ItemDroppedFromInventoryEvent)
        assert events[0].aggregate_id == aggregate.player_id
        assert events[0].item_instance_id == ItemInstanceId(100)
        assert events[0].slot_id == SlotId(0)

    def test_drop_item_from_empty_slot(self):
        """空のスロットからアイテムを捨てようとすると例外が発生すること"""
        aggregate = create_test_inventory_aggregate(max_slots=5)

        with pytest.raises(ItemNotInSlotException):
            aggregate.drop_item(SlotId(0))

    def test_request_equip_item_normal(self):
        """アイテム装備を正常に要求できること"""
        aggregate = create_test_inventory_aggregate(
            inventory_slots={0: 100}
        )

        aggregate.request_equip_item(SlotId(0), EquipmentSlotType.WEAPON)

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], ItemEquipRequestedEvent)
        assert events[0].aggregate_id == aggregate.player_id
        assert events[0].inventory_slot_id == SlotId(0)
        assert events[0].item_instance_id == ItemInstanceId(100)
        assert events[0].target_equipment_slot == EquipmentSlotType.WEAPON

    def test_request_equip_item_from_empty_slot(self):
        """空のスロットから装備要求で例外が発生すること"""
        aggregate = create_test_inventory_aggregate(max_slots=5)

        with pytest.raises(ItemNotInSlotException):
            aggregate.request_equip_item(SlotId(0), EquipmentSlotType.WEAPON)

    def test_complete_equip_item_normal(self):
        """装備要求に対する実際の装備処理が正常に完了すること"""
        aggregate = create_test_inventory_aggregate(
            max_slots=5,
            inventory_slots={0: 100}
        )

        aggregate.complete_equip_item(
            inventory_slot_id=SlotId(0),
            equipment_slot=EquipmentSlotType.WEAPON,
            item_instance_id=ItemInstanceId(100)
        )

        # インベントリスロットが空になり、装備スロットにアイテムが移動していることを確認
        assert aggregate.get_item_instance_id_by_slot(SlotId(0)) is None
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.WEAPON) == ItemInstanceId(100)

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], ItemEquippedEvent)
        assert events[0].aggregate_id == aggregate.player_id
        assert events[0].item_instance_id == ItemInstanceId(100)
        assert events[0].from_slot_id == SlotId(0)
        assert events[0].to_equipment_slot == EquipmentSlotType.WEAPON

    def test_complete_equip_item_with_replacement_has_space(self):
        """既存の装備を置き換える場合、インベントリに空きがあれば既存装備がインベントリに戻されること"""
        aggregate = create_test_inventory_aggregate(
            max_slots=5,
            inventory_slots={0: 100},
            equipment_slots={EquipmentSlotType.WEAPON: 200}  # 既に装備あり
        )

        aggregate.complete_equip_item(
            inventory_slot_id=SlotId(0),
            equipment_slot=EquipmentSlotType.WEAPON,
            item_instance_id=ItemInstanceId(100)
        )

        # インベントリスロットが空になり、装備スロットが置き換わっていることを確認
        assert aggregate.get_item_instance_id_by_slot(SlotId(0)) is None
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.WEAPON) == ItemInstanceId(100)

        # 既存装備がインベントリの空きスロット（slot 1）に移動していることを確認
        assert aggregate.get_item_instance_id_by_slot(SlotId(1)) == ItemInstanceId(200)

        # 装備完了イベントのみが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1

        equip_event = events[0]
        assert isinstance(equip_event, ItemEquippedEvent)
        assert equip_event.item_instance_id == ItemInstanceId(100)

    def test_complete_equip_item_with_replacement_inventory_full(self):
        """既存装備置き換え時にインベントリが満杯の場合、オーバーフローイベントと装備完了イベントが両方発行されること"""
        # インベントリを満杯にする
        occupied_slots = {i: 1000 + i for i in range(5)}
        aggregate = create_test_inventory_aggregate(
            max_slots=5,
            inventory_slots=occupied_slots,
            equipment_slots={EquipmentSlotType.WEAPON: 200}
        )

        # 装備処理を実行（インベントリに空きがない）
        aggregate.complete_equip_item(
            inventory_slot_id=SlotId(0),  # 仮に空いていたと仮定
            equipment_slot=EquipmentSlotType.WEAPON,
            item_instance_id=ItemInstanceId(100)
        )

        # 装備スロットが正しく更新されていることを確認
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.WEAPON) == ItemInstanceId(100)

        # オーバーフローイベントと装備完了イベントの両方が発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 2

        overflow_event = events[0]
        assert isinstance(overflow_event, InventorySlotOverflowEvent)
        assert overflow_event.overflowed_item_instance_id == ItemInstanceId(200)
        assert overflow_event.reason == "equip_replacement"

        equip_event = events[1]
        assert isinstance(equip_event, ItemEquippedEvent)
        assert equip_event.item_instance_id == ItemInstanceId(100)

    def test_unequip_item_normal(self):
        """装備アイテムを正常に外せること"""
        aggregate = create_test_inventory_aggregate(
            equipment_slots={EquipmentSlotType.WEAPON: 100}
        )

        aggregate.unequip_item(EquipmentSlotType.WEAPON)

        # 装備スロットが空になり、アイテムがインベントリの最初の空きスロットに移動していることを確認
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.WEAPON) is None
        assert aggregate.get_item_instance_id_by_slot(SlotId(0)) == ItemInstanceId(100)

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], ItemUnequippedEvent)
        assert events[0].aggregate_id == aggregate.player_id
        assert events[0].item_instance_id == ItemInstanceId(100)
        assert events[0].from_equipment_slot == EquipmentSlotType.WEAPON
        assert events[0].to_slot_id == SlotId(0)

    def test_unequip_item_empty_slot(self):
        """空の装備スロットから外そうとすると例外が発生すること"""
        aggregate = create_test_inventory_aggregate()

        with pytest.raises(ItemNotInSlotException):
            aggregate.unequip_item(EquipmentSlotType.WEAPON)

    def test_unequip_item_inventory_full(self):
        """装備解除時にインベントリが満杯の場合、オーバーフローイベントと装備解除イベントが両方発行されること"""
        # インベントリを満杯にする
        occupied_slots = {i: 1000 + i for i in range(5)}
        aggregate = create_test_inventory_aggregate(
            max_slots=5,
            inventory_slots=occupied_slots,
            equipment_slots={EquipmentSlotType.WEAPON: 100}
        )

        aggregate.unequip_item(EquipmentSlotType.WEAPON)

        # 装備スロットが空になっていることを確認
        assert aggregate.get_item_instance_id_by_equipment_slot(EquipmentSlotType.WEAPON) is None

        # オーバーフローイベントと装備解除イベントの両方が発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 2

        overflow_event = events[0]
        assert isinstance(overflow_event, InventorySlotOverflowEvent)
        assert overflow_event.overflowed_item_instance_id == ItemInstanceId(100)
        assert overflow_event.reason == "unequip_no_space"

        unequip_event = events[1]
        assert isinstance(unequip_event, ItemUnequippedEvent)
        assert unequip_event.item_instance_id == ItemInstanceId(100)
        assert unequip_event.from_equipment_slot == EquipmentSlotType.WEAPON
        assert unequip_event.to_slot_id is None  # インベントリに空きがないため

    def test_is_inventory_full(self):
        """インベントリ満杯状態が正しく判定されること"""
        # 空のインベントリ
        aggregate = create_test_inventory_aggregate(max_slots=3)
        assert aggregate.is_inventory_full() == False

        # 満杯のインベントリ
        occupied_slots = {0: 100, 1: 200, 2: 300}
        aggregate = create_test_inventory_aggregate(
            max_slots=3,
            inventory_slots=occupied_slots
        )
        assert aggregate.is_inventory_full() == True

    def test_get_inventory_summary(self):
        """インベントリの統計情報が正しく取得できること"""
        occupied_slots = {0: 100, 1: 200}  # 2スロット使用
        equipment_slots = {EquipmentSlotType.WEAPON: 300, EquipmentSlotType.ARMOR: 400}  # 2スロット使用

        aggregate = create_test_inventory_aggregate(
            max_slots=5,
            inventory_slots=occupied_slots,
            equipment_slots=equipment_slots
        )

        summary = aggregate.get_inventory_summary()

        assert summary["total_inventory_slots"] == 5
        assert summary["used_inventory_slots"] == 2
        assert summary["empty_inventory_slots"] == 3
        assert summary["equipped_slots"] == 2
        assert summary["total_equipment_slots"] == len(EquipmentSlotType)
        assert summary["is_inventory_full"] == False
        assert summary["is_inventory_empty"] == False

    def test_get_inventory_summary_full_inventory(self):
        """満杯インベントリの統計情報が正しく取得できること"""
        occupied_slots = {i: 100 + i for i in range(5)}  # 全スロット使用
        aggregate = create_test_inventory_aggregate(
            max_slots=5,
            inventory_slots=occupied_slots
        )

        summary = aggregate.get_inventory_summary()

        assert summary["total_inventory_slots"] == 5
        assert summary["used_inventory_slots"] == 5
        assert summary["empty_inventory_slots"] == 0
        assert summary["is_inventory_full"] == True
        assert summary["is_inventory_empty"] == False

    def test_get_inventory_summary_empty_inventory(self):
        """空インベントリの統計情報が正しく取得できること"""
        aggregate = create_test_inventory_aggregate(max_slots=5)

        summary = aggregate.get_inventory_summary()

        assert summary["total_inventory_slots"] == 5
        assert summary["used_inventory_slots"] == 0
        assert summary["empty_inventory_slots"] == 5
        assert summary["is_inventory_full"] == False
        assert summary["is_inventory_empty"] == True

    def test_request_inventory_compaction(self):
        """インベントリ整理要求が正常に処理されること"""
        aggregate = create_test_inventory_aggregate()

        aggregate.request_inventory_compaction()

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], InventoryCompactionRequestedEvent)
        assert events[0].aggregate_id == aggregate.player_id

    def test_complete_inventory_compaction(self):
        """整理結果によるインベントリ更新が正常に処理されること"""
        aggregate = create_test_inventory_aggregate(max_slots=5)

        # 整理後のスロット配置
        compacted_slots = {
            SlotId(0): ItemInstanceId(100),
            SlotId(1): ItemInstanceId(200),
            SlotId(2): None,
            SlotId(3): None,
            SlotId(4): None,
        }

        aggregate.complete_inventory_compaction(compacted_slots)

        # スロットが更新されていることを確認
        assert aggregate.get_item_instance_id_by_slot(SlotId(0)) == ItemInstanceId(100)
        assert aggregate.get_item_instance_id_by_slot(SlotId(1)) == ItemInstanceId(200)
        assert aggregate.get_item_instance_id_by_slot(SlotId(2)) is None

        # イベントは発行されない（complete_inventory_compactionではイベントを発行しない）
        events = aggregate.get_events()
        assert len(events) == 0

    def test_request_inventory_sort(self):
        """インベントリソート要求が正常に処理されること"""
        aggregate = create_test_inventory_aggregate()

        aggregate.request_inventory_sort(InventorySortType.ITEM_TYPE)

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], InventorySortRequestedEvent)
        assert events[0].aggregate_id == aggregate.player_id
        assert events[0].sort_criteria == InventorySortType.ITEM_TYPE

    def test_request_inventory_sort_default_criteria(self):
        """デフォルトのソート基準でソート要求が処理されること"""
        aggregate = create_test_inventory_aggregate()

        aggregate.request_inventory_sort()  # デフォルト引数を使用

        # イベントが発行されていることを確認
        events = aggregate.get_events()
        assert len(events) == 1
        assert isinstance(events[0], InventorySortRequestedEvent)
        assert events[0].sort_criteria == InventorySortType.ITEM_TYPE  # デフォルト値

    def test_validate_inventory_slots_valid(self):
        """有効なインベントリスロットデータがバリデーションを通過すること"""
        aggregate = create_test_inventory_aggregate(max_slots=5)

        # 有効なデータを準備
        valid_slots = {
            SlotId(0): ItemInstanceId(100),
            SlotId(2): ItemInstanceId(200),
            SlotId(4): None,
        }

        # バリデーションが例外を投げないことを確認
        try:
            aggregate._validate_inventory_slots(valid_slots)
        except Exception:
            pytest.fail("Valid inventory slots should not raise exception")

    def test_validate_inventory_slots_invalid_range(self):
        """範囲外のスロットIDを持つデータがバリデーションで例外を投げること"""
        aggregate = create_test_inventory_aggregate(max_slots=5)

        # 無効なデータを準備（max_slotsを超えるスロットID）
        invalid_slots = {
            SlotId(0): ItemInstanceId(100),
            SlotId(5): ItemInstanceId(200),  # 範囲外
        }

        with pytest.raises(InvalidSlotException):
            aggregate._validate_inventory_slots(invalid_slots)

    def test_validate_equipment_slots_valid(self):
        """有効な装備スロットデータがバリデーションを通過すること"""
        aggregate = create_test_inventory_aggregate()

        # 有効なデータを準備（全てのEquipmentSlotTypeを含む）
        valid_slots = create_test_equipment_slots({
            EquipmentSlotType.WEAPON: 100,
            EquipmentSlotType.ARMOR: 200,
        })

        # バリデーションが例外を投げないことを確認
        try:
            aggregate._validate_equipment_slots(valid_slots)
        except Exception:
            pytest.fail("Valid equipment slots should not raise exception")

    def test_validate_equipment_slots_missing_types(self):
        """必要な装備スロットタイプが欠けている場合、バリデーションで例外を投げること"""
        aggregate = create_test_inventory_aggregate()

        # 無効なデータを準備（一部のEquipmentSlotTypeが欠けている）
        invalid_slots = {
            EquipmentSlotType.WEAPON: ItemInstanceId(100),
            EquipmentSlotType.HELMET: ItemInstanceId(200),
            # ARMOR, SHIELD, BOOTS, ACCESSORY が欠けている
        }

        with pytest.raises(EquipmentSlotValidationException):
            aggregate._validate_equipment_slots(invalid_slots)

    def test_validate_equipment_slots_extra_types(self):
        """余分な装備スロットタイプがある場合、バリデーションで例外を投げること"""
        aggregate = create_test_inventory_aggregate()

        # 無効なデータを準備（存在しないEquipmentSlotTypeを含む）
        # 実際にはEnumの値しか存在しないので、このテストはスキップ
        # EquipmentSlotTypeは固定のenumなので、余分なタイプを追加することはできない
        pass

    def test_event_accumulation_multiple_operations(self):
        """複数の操作でイベントが正しく蓄積されること"""
        aggregate = create_test_inventory_aggregate(max_slots=5)

        # 複数の操作を実行
        aggregate.acquire_item(ItemInstanceId(100))  # slot 0に配置
        aggregate.acquire_item(ItemInstanceId(200))  # slot 1に配置
        aggregate.drop_item(SlotId(0))  # slot 0を空にする
        aggregate.request_equip_item(SlotId(1), EquipmentSlotType.WEAPON)  # slot 1のアイテムを装備要求
        aggregate.request_inventory_compaction()
        aggregate.request_inventory_sort(InventorySortType.RARITY)

        # イベントが正しく蓄積されていることを確認
        events = aggregate.get_events()
        assert len(events) == 6

        # イベントの順序と種類を確認
        assert isinstance(events[0], ItemAddedToInventoryEvent)
        assert events[0].item_instance_id == ItemInstanceId(100)

        assert isinstance(events[1], ItemAddedToInventoryEvent)
        assert events[1].item_instance_id == ItemInstanceId(200)

        assert isinstance(events[2], ItemDroppedFromInventoryEvent)
        assert events[2].item_instance_id == ItemInstanceId(100)

        assert isinstance(events[3], ItemEquipRequestedEvent)
        assert events[3].item_instance_id == ItemInstanceId(200)
        assert events[3].inventory_slot_id == SlotId(1)

        assert isinstance(events[4], InventoryCompactionRequestedEvent)

        assert isinstance(events[5], InventorySortRequestedEvent)
        assert events[5].sort_criteria == InventorySortType.RARITY

    def test_event_clearing(self):
        """イベントが正しくクリアされること"""
        aggregate = create_test_inventory_aggregate()

        # 操作を実行してイベントを生成
        aggregate.acquire_item(ItemInstanceId(100))
        assert len(aggregate.get_events()) == 1

        # イベントをクリア
        aggregate.clear_events()
        assert len(aggregate.get_events()) == 0

        # 再度操作を実行
        aggregate.acquire_item(ItemInstanceId(200))
        assert len(aggregate.get_events()) == 1
