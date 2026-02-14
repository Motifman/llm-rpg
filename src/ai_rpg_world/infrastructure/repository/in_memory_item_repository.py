from typing import List, Optional
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import InMemoryRepositoryBase


class InMemoryItemRepository(ItemRepository, InMemoryRepositoryBase):
    """アイテム集約のインメモリリポジトリ実装"""

    def generate_item_instance_id(self) -> ItemInstanceId:
        """新しいItemInstanceIdを生成"""
        new_id = self._data_store.next_item_instance_id
        self._data_store.next_item_instance_id += 1
        return ItemInstanceId(new_id)

    def find_by_id(self, item_instance_id: ItemInstanceId) -> Optional[ItemAggregate]:
        """IDで検索"""
        pending = self._get_pending_aggregate(item_instance_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._data_store.items.get(item_instance_id))

    def find_by_ids(self, item_instance_ids: List[ItemInstanceId]) -> List[ItemAggregate]:
        """IDのリストで検索"""
        return [x for iid in item_instance_ids for x in [self.find_by_id(iid)] if x is not None]

    def find_all(self) -> List[ItemAggregate]:
        """全件取得"""
        return [self._clone(item) for item in self._data_store.items.values()]

    def save(self, aggregate: ItemAggregate) -> ItemAggregate:
        """保存"""
        cloned_aggregate = self._clone(aggregate)
        def operation():
            self._data_store.items[cloned_aggregate.item_instance_id] = cloned_aggregate
            return cloned_aggregate
            
        self._register_aggregate(aggregate)
        self._register_pending_if_uow(aggregate.item_instance_id, aggregate)
        return self._execute_operation(operation)

    def delete(self, item_instance_id: ItemInstanceId) -> bool:
        """削除"""
        def operation():
            if item_instance_id in self._data_store.items:
                del self._data_store.items[item_instance_id]
                return True
            return False
        return self._execute_operation(operation)

    def find_by_spec_id(self, item_spec_id: ItemSpecId) -> List[ItemAggregate]:
        """アイテム仕様IDで検索"""
        return [
            item for item in self._data_store.items.values()
            if item.item_spec.item_spec_id == item_spec_id
        ]

    def find_by_type(self, item_type: ItemType) -> List[ItemAggregate]:
        """アイテムタイプで検索"""
        return [
            item for item in self._data_store.items.values()
            if item.item_spec.item_type == item_type
        ]

    def find_by_rarity(self, rarity: Rarity) -> List[ItemAggregate]:
        """レアリティで検索"""
        return [
            item for item in self._data_store.items.values()
            if item.item_spec.rarity == rarity
        ]

    def find_broken_items(self) -> List[ItemAggregate]:
        """破損したアイテムを検索"""
        return [
            item for item in self._data_store.items.values()
            if item.is_broken
        ]

    def find_tradeable_items(self) -> List[ItemAggregate]:
        """取引可能なアイテムを検索"""
        # クエストアイテム以外を取引可能とする例
        return [
            item for item in self._data_store.items.values()
            if item.item_spec.item_type != ItemType.QUEST
        ]

    def find_by_owner_id(self, owner_id: int) -> List[ItemAggregate]:
        """所有者IDで検索（この実装では未サポートだが、将来用）"""
        return []
