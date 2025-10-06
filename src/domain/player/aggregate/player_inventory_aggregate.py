from typing import Optional
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.item.item_quantity import ItemQuantity
from src.domain.item.unique_item import UniqueItem
from src.domain.player.value_object.player_id import PlayerId
from src.domain.player.value_object.player_inventory_id import PlayerInventoryId
from src.domain.player.value_object.inventory_slots import InventorySlots
from src.domain.player.event.inventory_events import ItemAddedToInventoryEvent, ItemRemovedFromInventoryEvent


class PlayerInventoryAggregate(AggregateRoot):
    """プレイヤーインベントリ集約"""

    def __init__(
        self,
        inventory_id: PlayerInventoryId,
        player_id: PlayerId,
        slots: InventorySlots
    ):
        super().__init__()
        self._inventory_id = inventory_id
        self._player_id = player_id
        self._slots = slots

    @classmethod
    def create_new_inventory(
        cls,
        inventory_id: PlayerInventoryId,
        player_id: PlayerId,
        max_slots: int = 20
    ) -> "PlayerInventoryAggregate":
        """新しいインベントリを作成"""
        slots = InventorySlots.create_empty(max_slots)
        return cls(inventory_id=inventory_id, player_id=player_id, slots=slots)

    @property
    def inventory_id(self) -> PlayerInventoryId:
        return self._inventory_id

    @property
    def player_id(self) -> PlayerId:
        return self._player_id

    @property
    def slots(self) -> InventorySlots:
        return self._slots

    @property
    def max_slots(self) -> int:
        return self._slots.max_slots

    @property
    def free_slots_count(self) -> int:
        return self._slots.get_free_slots_count()

    def is_full(self) -> bool:
        """インベントリが満杯かどうか"""
        return self._slots.is_full()

    def has_stackable(self, item_id: int, quantity: int) -> bool:
        """スタック可能アイテムを持っているかどうか"""
        return self._slots.has_stackable(item_id, quantity)

    def has_unique(self, unique_id: int) -> bool:
        """ユニークアイテムを持っているかどうか"""
        return self._slots.has_unique(unique_id)

    def add_item(self, item: ItemQuantity | UniqueItem) -> None:
        """アイテムを追加"""
        try:
            new_slots = self._slots.with_item_added(item)

            # イベント発行
            if isinstance(item, ItemQuantity):
                event = ItemAddedToInventoryEvent.create(
                    aggregate_id=self._inventory_id,
                    aggregate_type="PlayerInventoryAggregate",
                    player_id=self._player_id.value,
                    item_id=item.item.item_id,
                    quantity=item.quantity
                )
            else:  # UniqueItem
                event = ItemAddedToInventoryEvent.create(
                    aggregate_id=self._inventory_id,
                    aggregate_type="PlayerInventoryAggregate",
                    player_id=self._player_id.value,
                    item_id=item.item_id,
                    unique_id=item.unique_id
                )
            self.add_event(event)

            # 状態更新
            self._slots = new_slots

        except ValueError as e:
            raise ValueError(f"Failed to add item to inventory: {e}")

    def remove_item(
        self,
        item_id: int = None,
        quantity: int = 1,
        unique_id: Optional[int] = None,
        slot_id: Optional[int] = None
    ) -> Optional[ItemQuantity | UniqueItem]:
        """アイテムを削除"""
        removed_item, new_slots = self._slots.with_item_removed(
            item_id=item_id,
            quantity=quantity,
            unique_id=unique_id,
            slot_id=slot_id
        )

        if removed_item:
            # イベント発行
            if isinstance(removed_item, ItemQuantity):
                event = ItemRemovedFromInventoryEvent.create(
                    aggregate_id=self._inventory_id,
                    aggregate_type="PlayerInventoryAggregate",
                    player_id=self._player_id.value,
                    item_id=removed_item.item.item_id,
                    quantity=removed_item.quantity
                )
            else:  # UniqueItem
                event = ItemRemovedFromInventoryEvent.create(
                    aggregate_id=self._inventory_id,
                    aggregate_type="PlayerInventoryAggregate",
                    player_id=self._player_id.value,
                    item_id=removed_item.item_id,
                    unique_id=removed_item.unique_id
                )
            self.add_event(event)

            # 状態更新
            self._slots = new_slots

        return removed_item

    def get_total_quantity(self, item_id: int) -> int:
        """指定アイテムの総数量を取得"""
        return self._slots.get_total_quantity_by_item_id(item_id)

    def get_slot_by_id(self, slot_id: int):
        """スロットIDでスロットを取得"""
        return self._slots.get_slot_by_id(slot_id)

    def can_add_item(self, item: ItemQuantity | UniqueItem) -> bool:
        """アイテムを追加できるかどうか"""
        try:
            self._slots.with_item_added(item)
            return True
        except ValueError:
            return False
