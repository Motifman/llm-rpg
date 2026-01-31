import pytest
from src.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from src.domain.player.value_object.player_id import PlayerId
from src.domain.player.value_object.slot_id import SlotId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.player.enum.equipment_slot_type import EquipmentSlotType
from src.domain.player.event.inventory_events import (
    ItemReservedForTradeEvent,
    ItemReservationCancelledEvent,
    ItemDroppedFromInventoryEvent
)
from src.domain.player.exception.player_exceptions import (
    ItemReservedException,
    ItemAlreadyReservedException,
    ItemNotReservedException,
    ItemNotInSlotException
)

def setup_inventory(max_slots=5, occupied_slots=None):
    player_id = PlayerId(1)
    inventory_slots = {SlotId(i): None for i in range(max_slots)}
    if occupied_slots:
        for slot_idx, item_id in occupied_slots.items():
            inventory_slots[SlotId(slot_idx)] = ItemInstanceId(item_id)
    
    equipment_slots = {etype: None for etype in EquipmentSlotType}
    
    return PlayerInventoryAggregate.restore_from_data(
        player_id=player_id,
        max_slots=max_slots,
        inventory_slots=inventory_slots,
        equipment_slots=equipment_slots,
        reserved_item_ids=set()
    )

class TestPlayerInventoryReservation:
    def test_reserve_item_success(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        item_id = ItemInstanceId(100)
        
        # 予約実行
        reserved_id = inventory.reserve_item(SlotId(0))
        
        assert reserved_id == item_id
        assert inventory.is_item_reserved(item_id) is True
        
        # イベント確認
        events = inventory.get_events()
        assert any(isinstance(e, ItemReservedForTradeEvent) and e.item_instance_id == item_id for e in events)

    def test_reserve_item_already_reserved(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        inventory.reserve_item(SlotId(0))
        
        with pytest.raises(ItemAlreadyReservedException):
            inventory.reserve_item(SlotId(0))

    def test_reserve_empty_slot(self):
        inventory = setup_inventory()
        with pytest.raises(ItemNotInSlotException):
            inventory.reserve_item(SlotId(0))

    def test_unreserve_item_success(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        item_id = ItemInstanceId(100)
        inventory.reserve_item(SlotId(0))
        inventory.clear_events()
        
        # 予約解除
        inventory.unreserve_item(item_id)
        
        assert inventory.is_item_reserved(item_id) is False
        
        # イベント確認
        events = inventory.get_events()
        assert any(isinstance(e, ItemReservationCancelledEvent) and e.item_instance_id == item_id for e in events)

    def test_remove_reserved_item_success(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        item_id = ItemInstanceId(100)
        inventory.reserve_item(SlotId(0))
        inventory.clear_events()
        
        # 予約済みアイテムの削除（成約時）
        inventory.remove_reserved_item(item_id)
        
        assert inventory.get_item_instance_id_by_slot(SlotId(0)) is None
        assert inventory.is_item_reserved(item_id) is False
        
        # アイテム削除イベントが発行されること
        events = inventory.get_events()
        assert any(isinstance(e, ItemDroppedFromInventoryEvent) and e.item_instance_id == item_id for e in events)

    def test_remove_non_reserved_item(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        item_id = ItemInstanceId(100)
        
        with pytest.raises(ItemNotReservedException):
            inventory.remove_reserved_item(item_id)

    def test_drop_reserved_item_should_fail(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        inventory.reserve_item(SlotId(0))
        
        with pytest.raises(ItemReservedException):
            inventory.drop_item(SlotId(0))

    def test_move_reserved_item_should_fail(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        inventory.reserve_item(SlotId(0))
        
        with pytest.raises(ItemReservedException):
            inventory.move_item(SlotId(0), SlotId(1))

    def test_equip_reserved_item_should_fail(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        inventory.reserve_item(SlotId(0))
        
        with pytest.raises(ItemReservedException):
            inventory.request_equip_item(SlotId(0), EquipmentSlotType.WEAPON)

    def test_complete_equip_reserved_item_should_fail(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        item_id = ItemInstanceId(100)
        inventory.reserve_item(SlotId(0))
        
        with pytest.raises(ItemReservedException):
            inventory.complete_equip_item(SlotId(0), EquipmentSlotType.WEAPON, item_id)

    def test_remove_reserved_item_not_in_slot(self):
        # 予約リストにはあるが、何らかの理由でスロットから消えている不整合ケース
        inventory = setup_inventory(occupied_slots={0: 100})
        item_id = ItemInstanceId(100)
        inventory.reserve_item(SlotId(0))
        
        # 強制的にスロットから消す（内部状態を直接操作）
        inventory._inventory_slots[SlotId(0)] = None
        
        with pytest.raises(ItemNotInSlotException):
            inventory.remove_reserved_item(item_id)
        
        # 整合性確保のため、予約リストからも消えているべき
        assert inventory.is_item_reserved(item_id) is False

    def test_unreserve_non_reserved_item(self):
        inventory = setup_inventory(occupied_slots={0: 100})
        item_id = ItemInstanceId(100)
        
        # 予約されていないアイテムを解除してもエラーにならない
        inventory.unreserve_item(item_id)
        assert inventory.is_item_reserved(item_id) is False
        
        # イベントは発行されないこと
        assert len(inventory.get_events()) == 0
