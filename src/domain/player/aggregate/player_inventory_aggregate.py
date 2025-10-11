from typing import Optional, Dict, Any
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.enum.item_enum import EquipmentType
from src.domain.player.enum.equipment_slot_type import EquipmentSlotType
from src.domain.player.enum.inventory_sort_type import InventorySortType
from src.domain.player.value_object.player_id import PlayerId
from src.domain.player.value_object.slot_id import SlotId
from src.domain.player.event.inventory_events import (
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
from src.domain.player.exception.player_exceptions import (
    InventoryFullException,
    InvalidSlotException,
    ItemNotInSlotException,
    EquipmentSlotOccupiedException,
    EquipmentSlotValidationException
)


class PlayerInventoryAggregate(AggregateRoot):
    """プレイヤーインベントリ集約

    ItemInstanceIdのみを保持し、アイテムの状態管理はItemAggregateに委ねる。
    装備スロットはEquipmentTypeごとに管理する。
    """
    DEFAULT_MAX_SLOTS = 20

    def __init__(
        self,
        player_id: PlayerId,
        max_slots: int = DEFAULT_MAX_SLOTS,
        inventory_slots: Optional[Dict[SlotId, Optional[ItemInstanceId]]] = None,
        equipment_slots: Optional[Dict[EquipmentSlotType, Optional[ItemInstanceId]]] = None
    ):
        super().__init__()
        self._player_id = player_id
        self._max_slots = max_slots

        # インベントリスロット: slot_id -> item_instance_id
        if inventory_slots is not None:
            # 既存データを入力する場合
            self._validate_inventory_slots(inventory_slots)
            self._inventory_slots = inventory_slots.copy()
        else:
            # 新規作成の場合
            self._inventory_slots: Dict[SlotId, Optional[ItemInstanceId]] = {}
            for i in range(max_slots):
                self._inventory_slots[SlotId(i)] = None

        # 装備スロット: equipment_slot_type -> item_instance_id
        if equipment_slots is not None:
            # 既存データを入力する場合
            self._validate_equipment_slots(equipment_slots)
            self._equipment_slots = equipment_slots.copy()
        else:
            # 新規作成の場合
            self._equipment_slots: Dict[EquipmentSlotType, Optional[ItemInstanceId]] = {}
            for equipment_slot_type in EquipmentSlotType:
                self._equipment_slots[equipment_slot_type] = None

    @classmethod
    def create_new_inventory(
        cls,
        player_id: PlayerId,
        max_slots: int = DEFAULT_MAX_SLOTS
    ) -> "PlayerInventoryAggregate":
        """新しいインベントリを作成"""
        return cls(player_id=player_id, max_slots=max_slots)

    @classmethod
    def restore_from_data(
        cls,
        player_id: PlayerId,
        max_slots: int,
        inventory_slots: Dict[SlotId, Optional[ItemInstanceId]],
        equipment_slots: Dict[EquipmentSlotType, Optional[ItemInstanceId]]
    ) -> "PlayerInventoryAggregate":
        """既存データからインベントリを復元"""
        return cls(
            player_id=player_id,
            max_slots=max_slots,
            inventory_slots=inventory_slots,
            equipment_slots=equipment_slots
        )

    @property
    def player_id(self) -> PlayerId:
        return self._player_id

    @property
    def max_slots(self) -> int:
        return self._max_slots

    def get_item_instance_id_by_slot(self, slot_id: SlotId) -> Optional[ItemInstanceId]:
        """スロット番号からItemInstanceIdを取得"""
        if slot_id.value >= self._max_slots:
            raise InvalidSlotException(f"Invalid slot id: {slot_id.value}")
        return self._inventory_slots.get(slot_id)

    def get_item_instance_id_by_equipment_slot(self, equipment_slot: EquipmentSlotType) -> Optional[ItemInstanceId]:
        """装備スロットタイプからItemInstanceIdを取得"""
        return self._equipment_slots.get(equipment_slot)

    def acquire_item(self, item_instance_id: ItemInstanceId) -> None:
        """アイテムを入手する（アイテム入手イベントを発行）"""
        # 空きスロットを探す
        empty_slot = self._find_empty_inventory_slot()
        if empty_slot is None:
            raise InventoryFullException("Inventory is full")

        # アイテムを配置
        self._inventory_slots[empty_slot] = item_instance_id

        # イベント発行
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=item_instance_id
        )
        self.add_event(event)

    def move_item(self, from_slot: SlotId, to_slot: SlotId) -> None:
        """インベントリスロット間でアイテムを移動する"""
        # 移動元スロットのバリデーション
        if from_slot == to_slot:
            raise InvalidSlotException("Cannot move item to the same slot")

        from_item = self.get_item_instance_id_by_slot(from_slot)
        if from_item is None:
            raise ItemNotInSlotException(f"No item in slot {from_slot.value}")

        # 移動先スロットのバリデーション
        to_item = self.get_item_instance_id_by_slot(to_slot)
        if to_item is not None:
            raise InvalidSlotException(f"Destination slot {to_slot.value} is not empty")

        # アイテムを移動
        self._inventory_slots[from_slot] = None
        self._inventory_slots[to_slot] = from_item

    def drop_item(self, slot_id: SlotId) -> None:
        """アイテムを捨てる（捨てるイベントを発行）"""
        item_instance_id = self.get_item_instance_id_by_slot(slot_id)
        if item_instance_id is None:
            raise ItemNotInSlotException(f"No item in slot {slot_id.value}")

        # スロットを空にする
        self._inventory_slots[slot_id] = None

        # イベント発行
        event = ItemDroppedFromInventoryEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=item_instance_id,
            slot_id=slot_id
        )
        self.add_event(event)

    def request_equip_item(self, inventory_slot_id: SlotId, equipment_slot: EquipmentSlotType) -> None:
        """アイテム装備を要求する（装備要求イベントを発行）"""
        # インベントリスロットからアイテムを取得
        item_instance_id = self.get_item_instance_id_by_slot(inventory_slot_id)
        if item_instance_id is None:
            raise ItemNotInSlotException(f"No item in inventory slot {inventory_slot_id.value}")

        # 装備要求イベントを発行（バリデーションはイベントハンドラで行う）
        event = ItemEquipRequestedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerInventoryAggregate",
            inventory_slot_id=inventory_slot_id,
            item_instance_id=item_instance_id,
            target_equipment_slot=equipment_slot
        )
        self.add_event(event)

    def complete_equip_item(self, inventory_slot_id: SlotId, equipment_slot: EquipmentSlotType, item_instance_id: ItemInstanceId) -> None:
        """装備要求に対する実際の装備処理を実行"""
        # 現在の装備をチェック
        current_equipped = self._equipment_slots.get(equipment_slot)
        if current_equipped is not None:
            # 既存の装備をインベントリに戻す
            empty_slot = self._find_empty_inventory_slot()
            if empty_slot is None:
                # インベントリが満杯の場合、オーバーフローイベントを発行
                overflow_event = InventorySlotOverflowEvent.create(
                    aggregate_id=self._player_id,
                    aggregate_type="PlayerInventoryAggregate",
                    overflowed_item_instance_id=current_equipped,
                    reason="equip_replacement"
                )
                self.add_event(overflow_event)
            else:
                # 既存装備をインベントリに戻す
                self._inventory_slots[empty_slot] = current_equipped

        # 装備スロットに移動
        self._inventory_slots[inventory_slot_id] = None
        self._equipment_slots[equipment_slot] = item_instance_id

        # 装備完了イベント発行
        event = ItemEquippedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=item_instance_id,
            from_slot_id=inventory_slot_id,
            to_equipment_slot=equipment_slot
        )
        self.add_event(event)

    def unequip_item(self, equipment_slot: EquipmentSlotType) -> None:
        """装備アイテムを外す"""
        item_instance_id = self._equipment_slots.get(equipment_slot)
        if item_instance_id is None:
            raise ItemNotInSlotException(f"No item equipped in {equipment_slot.value} slot")

        # インベントリの空きスロットを探す
        empty_slot = self._find_empty_inventory_slot()
        if empty_slot is None:
            # インベントリが満杯の場合、オーバーフローイベントを発行
            overflow_event = InventorySlotOverflowEvent.create(
                aggregate_id=self._player_id,
                aggregate_type="PlayerInventoryAggregate",
                overflowed_item_instance_id=item_instance_id,
                reason="unequip_no_space"
            )
            self.add_event(overflow_event)
        else:
            # インベントリに戻す
            self._inventory_slots[empty_slot] = item_instance_id

        # 装備スロットを空にする
        self._equipment_slots[equipment_slot] = None

        # イベント発行
        event = ItemUnequippedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=item_instance_id,
            from_equipment_slot=equipment_slot,
            to_slot_id=empty_slot if empty_slot is not None else None
        )
        self.add_event(event)

    def _find_empty_inventory_slot(self) -> Optional[SlotId]:
        """空のインベントリスロットを探す"""
        for slot_id, item_instance_id in self._inventory_slots.items():
            if item_instance_id is None:
                return slot_id
        return None

    def is_inventory_full(self) -> bool:
        """インベントリが満杯かどうか"""
        return self._find_empty_inventory_slot() is None

    def get_inventory_summary(self) -> Dict[str, Any]:
        """インベントリの統計情報取得"""
        # インベントリスロットの使用状況
        used_inventory_slots = sum(1 for item_id in self._inventory_slots.values() if item_id is not None)
        empty_inventory_slots = self._max_slots - used_inventory_slots

        # 装備スロットの使用状況
        equipped_slots = sum(1 for item_id in self._equipment_slots.values() if item_id is not None)

        return {
            "total_inventory_slots": self._max_slots,
            "used_inventory_slots": used_inventory_slots,
            "empty_inventory_slots": empty_inventory_slots,
            "equipped_slots": equipped_slots,
            "total_equipment_slots": len(EquipmentSlotType),
            "is_inventory_full": self.is_inventory_full(),
            "is_inventory_empty": used_inventory_slots == 0
        }

    def request_inventory_compaction(self) -> None:
        """インベントリの整理要求（イベントを発行）"""
        # 整理要求イベントを発行（実際の整理処理はイベントハンドラで行う）
        event = InventoryCompactionRequestedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerInventoryAggregate"
        )
        self.add_event(event)

    def complete_inventory_compaction(self, compacted_slots: Dict[SlotId, Optional[ItemInstanceId]]) -> None:
        """整理結果によるインベントリの更新"""
        # 整理されたスロット情報を反映
        for slot_id, item_instance_id in compacted_slots.items():
            if slot_id.value < self._max_slots:
                self._inventory_slots[slot_id] = item_instance_id

    def request_inventory_sort(self, sort_criteria: InventorySortType = InventorySortType.ITEM_TYPE) -> None:
        """インベントリのソート要求（イベントを発行）

        Args:
            sort_criteria: ソート基準
        """
        # ソート要求イベントを発行（実際のソート処理はイベントハンドラで行う）
        event = InventorySortRequestedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerInventoryAggregate",
            sort_criteria=sort_criteria
        )
        self.add_event(event)

    def _validate_inventory_slots(self, slots: Dict[SlotId, Optional[ItemInstanceId]]) -> None:
        """インベントリスロットのバリデーション"""
        for slot_id in slots.keys():
            if slot_id.value < 0 or slot_id.value >= self._max_slots:
                raise InvalidSlotException(f"Inventory slot id {slot_id.value} is out of range [0, {self._max_slots})")

    def _validate_equipment_slots(self, slots: Dict[EquipmentSlotType, Optional[ItemInstanceId]]) -> None:
        """装備スロットのバリデーション"""
        expected_types = set(EquipmentSlotType)
        actual_types = set(slots.keys())
        if expected_types != actual_types:
            missing = expected_types - actual_types
            extra = actual_types - expected_types
            error_msg = "Equipment slots validation failed:"
            if missing:
                error_msg += f" missing types: {missing}"
            if extra:
                error_msg += f" extra types: {extra}"
            raise EquipmentSlotValidationException(error_msg)
