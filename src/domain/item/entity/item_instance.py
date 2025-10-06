from __future__ import annotations

from typing import Optional
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.value_object.item_spec import ItemSpec
from src.domain.item.value_object.durability import Durability
from src.domain.item.exception import (
    QuantityValidationException,
    DurabilityValidationException,
    StackSizeExceededException,
    InsufficientQuantityException,
)


class ItemInstance:
    """アイテムインスタンスエンティティ"""

    def __init__(
        self,
        item_instance_id: ItemInstanceId,
        item_spec: ItemSpec,
        durability: Optional[Durability] = None,
        quantity: int = 1
    ):
        self._item_instance_id = item_instance_id
        self._item_spec = item_spec
        self._durability = durability
        self._quantity = quantity

        self._validate()

    def _validate(self) -> None:
        """バリデーション"""
        if self._quantity < 0:
            raise QuantityValidationException(
                quantity=self._quantity,
                reason="quantity must be >= 0"
            )
        if self._quantity > self._item_spec.max_stack_size.value:
            raise StackSizeExceededException(f"Stack size exceeded: current {self._quantity}, max {self._item_spec.max_stack_size.value}")
        # 耐久度が存在する場合、max_stack_sizeは1でなければならない
        if self._durability is not None and self._item_spec.max_stack_size.value != 1:
            raise DurabilityValidationException(f"Items with durability must have max_stack_size of 1, but spec has {self._item_spec.max_stack_size.value}")
        if self._durability is not None and self._item_spec.durability_max is None:
            raise DurabilityValidationException(f"Cannot have durability for item without durability_max in spec")
        if self._durability is not None and self._durability.max_value != self._item_spec.durability_max:
            raise DurabilityValidationException(f"Durability max_value ({self._durability.max_value}) must match spec durability_max ({self._item_spec.durability_max})")

    @property
    def item_instance_id(self) -> ItemInstanceId:
        """アイテムインスタンスID"""
        return self._item_instance_id

    @property
    def item_spec(self) -> ItemSpec:
        """アイテム仕様"""
        return self._item_spec

    @property
    def name(self) -> str:
        """アイテム名"""
        return self._item_spec.name

    @property
    def item_type(self):
        """アイテムタイプ"""
        return self._item_spec.item_type

    @property
    def description(self) -> str:
        """アイテム説明"""
        return self._item_spec.description

    @property
    def max_stack_size(self):
        """最大スタックサイズ"""
        return self._item_spec.max_stack_size

    @property
    def durability(self) -> Optional[Durability]:
        """耐久度"""
        return self._durability

    @property
    def quantity(self) -> int:
        """現在の数量"""
        return self._quantity

    def use(self) -> bool:
        """アイテムを使用する（副作用あり）

        Returns:
            bool: 使用に成功したかどうか
        """
        # 耐久度がある場合は先に使用
        if self._durability:
            new_durability, durability_success = self._durability.use()
            if not durability_success:
                return False  # 破損

            # 耐久度が更新された場合、状態を更新
            if new_durability != self._durability:
                self._durability = new_durability
                return True

        # 数量を減らす（1以上の場合）
        if self._quantity > 1:
            self._quantity -= 1
            return True

        # 数量が1で耐久度がない場合、または耐久度が正常に使用された場合
        return True

    def can_stack_with(self, other: 'ItemInstance') -> bool:
        """他のアイテムインスタンスとスタック可能かどうか

        以下の条件を全て満たす場合にスタック可能：
        - スペックが同じ
        - 現在の数量が最大スタックサイズ未満
        - 両方のアイテムが耐久度を持たない（耐久度付きアイテムはスタック不可）

        Args:
            other: 比較対象のアイテムインスタンス

        Returns:
            bool: スタック可能かどうか
        """
        # 耐久度仕様を持つアイテムはスタックできない（durability_maxが設定されている場合）
        if self._item_spec.durability_max is not None or other._item_spec.durability_max is not None:
            return False

        # 耐久度インスタンスが存在する場合はスタックできない
        if self._durability is not None or other._durability is not None:
            return False

        return (
            self._item_spec == other._item_spec and
            self._quantity < self._item_spec.max_stack_size.value
        )

    def add_quantity(self, amount: int) -> None:
        """数量を追加する

        Args:
            amount: 追加する数量

        Raises:
            StackSizeExceededException: 最大スタックサイズを超える場合
        """
        if amount <= 0:
            raise QuantityValidationException(
                quantity=amount,
                reason="amount must be positive"
            )

        new_quantity = self._quantity + amount
        if new_quantity > self._item_spec.max_stack_size.value:
            raise StackSizeExceededException(f"Adding {amount} would exceed stack size: current {self._quantity}, max {self._item_spec.max_stack_size.value}")

        self._quantity = new_quantity

    def remove_quantity(self, amount: int) -> None:
        """数量を減らす

        Args:
            amount: 減らす数量

        Raises:
            InsufficientQuantityException: 数量が不足する場合
        """
        if amount <= 0:
            raise QuantityValidationException(
                quantity=amount,
                reason="amount must be positive"
            )

        if amount > self._quantity:
            raise InsufficientQuantityException(
                requested=amount,
                available=self._quantity
            )

        self._quantity -= amount

    def set_quantity(self, quantity: int) -> None:
        """数量を直接設定する

        Args:
            quantity: 設定する数量

        Raises:
            StackSizeExceededException: 最大スタックサイズを超える場合
        """
        if quantity <= 0:
            raise QuantityValidationException(
                quantity=quantity,
                reason="quantity must be positive"
            )

        if quantity > self._item_spec.max_stack_size.value:
            raise StackSizeExceededException(
                current_quantity=quantity,
                max_stack_size=self._item_spec.max_stack_size.value
            )

        self._quantity = quantity

    def repair_durability(self, amount: int = 1) -> None:
        """耐久度を回復する

        Args:
            amount: 回復する量
        """
        if self._durability is None:
            return

        new_durability = self._durability.repair(amount)
        self._durability = new_durability

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, ItemInstance):
            return NotImplemented
        return self._item_instance_id == other._item_instance_id

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash(self._item_instance_id)

    def __repr__(self) -> str:
        """文字列表現"""
        id_str = str(self._item_instance_id.value)[:8]
        return f"ItemInstance(id={id_str}, name={self._item_spec.name}, qty={self._quantity})"
