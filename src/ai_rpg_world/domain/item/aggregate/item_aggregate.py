from typing import Optional
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.durability import Durability
from ai_rpg_world.domain.item.event.item_event import ItemUsedEvent, ItemBrokenEvent, ItemCraftedEvent, ItemRepairedEvent


class ItemAggregate(AggregateRoot):
    """アイテム集約

    ItemInstanceをルートエンティティとして扱い、
    アイテムの使用・破損などのライフサイクルを管理する。
    """

    def __init__(
        self,
        item_instance: ItemInstance
    ):
        super().__init__()
        self._item_instance = item_instance

    @classmethod
    def create(
        cls,
        item_instance_id: ItemInstanceId,
        item_spec: ItemSpec,
        durability: Optional[Durability] = None,
        quantity: int = 1
    ) -> "ItemAggregate":
        """新しいアイテム集約を作成"""
        # ビジネスルール: durability_maxがない場合にdurabilityを指定することはできない
        if durability is not None and item_spec.durability_max is None:
            from ai_rpg_world.domain.item.exception import DurabilityValidationException
            raise DurabilityValidationException(
                f"Cannot specify durability for item spec without durability_max (current: {durability.current}, max: {durability.max_value})"
            )

        item_instance = ItemInstance(
            item_instance_id=item_instance_id,
            item_spec=item_spec,
            durability=durability,
            quantity=quantity
        )
        return cls(item_instance)

    @classmethod
    def create_by_crafting(
        cls,
        item_instance_id: ItemInstanceId,
        item_spec: ItemSpec,
        quantity: int = 1
    ) -> "ItemAggregate":
        """合成によって作成されたアイテム集約を作成"""
        # 耐久度を持つアイテムの場合のみ耐久度を作成
        durability = None
        if item_spec.durability_max is not None:
            durability = Durability(current=item_spec.durability_max, max_value=item_spec.durability_max)

        item_instance = ItemInstance(
            item_instance_id=item_instance_id,
            item_spec=item_spec,
            durability=durability,
            quantity=quantity
        )
        event = ItemCraftedEvent.create(
            aggregate_id=item_instance_id,
            aggregate_type="ItemAggregate",
            item_instance_id=item_instance_id,
            item_spec_id=item_spec.item_spec_id,
            quantity=quantity
        )
        item_aggregate = cls(item_instance)
        item_aggregate.add_event(event)
        return item_aggregate

    @classmethod
    def create_from_instance(cls, item_instance: ItemInstance) -> "ItemAggregate":
        """既存のItemInstanceから集約を作成"""
        return cls(item_instance)

    @property
    def item_instance_id(self) -> ItemInstanceId:
        """アイテムインスタンスID"""
        return self._item_instance.item_instance_id

    @property
    def item_instance(self) -> ItemInstance:
        """アイテムインスタンス（内部エンティティ）"""
        return self._item_instance

    @property
    def item_spec(self) -> ItemSpec:
        """アイテム仕様"""
        return self._item_instance.item_spec

    @property
    def durability(self) -> Optional[Durability]:
        """耐久度"""
        return self._item_instance.durability

    @property
    def quantity(self) -> int:
        """現在の数量"""
        return self._item_instance.quantity

    @property
    def is_broken(self) -> bool:
        """破損しているかどうか"""
        return self.durability is not None and self.durability.is_broken

    def use(self) -> None:
        """アイテムを使用する

        使用成功時はItemUsedEventを発行し、
        破損時は追加でItemBrokenEventを発行する。
        """
        success = self._item_instance.use()

        if success:
            # 使用成功イベントを発行
            event = ItemUsedEvent.create(
                aggregate_id=self.item_instance_id,
                aggregate_type="ItemAggregate",
                item_instance_id=self.item_instance_id,
                item_spec_id=self.item_spec.item_spec_id,
                remaining_quantity=self.quantity,
                remaining_durability=self.durability
            )
            self.add_event(event)

            # 破損チェック
            if self.durability and self.durability.is_broken:
                broken_event = ItemBrokenEvent.create(
                    aggregate_id=self.item_instance_id,
                    aggregate_type="ItemAggregate",
                    item_instance_id=self.item_instance_id,
                    item_spec_id=self.item_spec.item_spec_id
                )
                self.add_event(broken_event)

    def can_stack_with(self, other: "ItemAggregate") -> bool:
        """他のアイテム集約とスタック可能かどうか"""
        return self._item_instance.can_stack_with(other._item_instance)

    def add_quantity(self, amount: int) -> None:
        """数量を追加する（副作用のある操作）"""
        self._item_instance.add_quantity(amount)

    def remove_quantity(self, amount: int) -> None:
        """数量を減らす（副作用のある操作）"""
        self._item_instance.remove_quantity(amount)

    def set_quantity(self, quantity: int) -> None:
        """数量を直接設定する（副作用のある操作）"""
        self._item_instance.set_quantity(quantity)

    def repair_durability(self, amount: int = 1) -> None:
        """耐久度を回復する

        Args:
            amount: 回復する量
        """
        old_durability = self.durability
        self._item_instance.repair_durability(amount)

        # 耐久度が変化した場合のみイベントを発行
        if old_durability != self.durability:
            event = ItemRepairedEvent.create(
                aggregate_id=self.item_instance_id,
                aggregate_type="ItemAggregate",
                item_instance_id=self.item_instance_id,
                item_spec_id=self.item_spec.item_spec_id,
                new_durability=self.durability
            )
            self.add_event(event)

    def get_item_info(self) -> dict:
        """アイテム情報を取得（DTO変換用）

        Returns:
            dict: アイテムの情報
        """
        return {
            "item_spec_id": self.item_spec.item_spec_id.value,
            "name": self.item_spec.name,
            "item_type": self.item_spec.item_type,
            "rarity": self.item_spec.rarity,
            "description": self.item_spec.description,
            "max_stack_size": self.item_spec.max_stack_size.value,
            "durability_max": self.item_spec.durability_max,
            "quantity": self.quantity,
            "current_durability": self.durability.current if self.durability else None,
            "is_broken": self.is_broken
        }
