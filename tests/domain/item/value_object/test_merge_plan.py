from dataclasses import replace

import pytest

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.exception import QuantityValidationException
from ai_rpg_world.domain.item.value_object.durability import Durability
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.value_object.merge_plan import (
    ConsumedItem,
    CraftingConsumptionPlan,
    CreateOperation,
    DeleteOperation,
    MergePlan,
    UpdateOperation,
)


class TestUpdateOperation:
    """UpdateOperationのテスト"""

    @pytest.fixture
    def sample_item_instance_id(self):
        """テスト用のItemInstanceIdを作成"""
        return ItemInstanceId(1)

    def test_update_operation_immutable(self, sample_item_instance_id):
        """UpdateOperationの不変性テスト"""
        operation = UpdateOperation(item_instance_id=sample_item_instance_id, new_quantity=5)

        with pytest.raises(AttributeError):
            operation.new_quantity = 20

        with pytest.raises(AttributeError):
            operation.item_instance_id = ItemInstanceId(999)

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_update_operation_rejects_non_positive_quantity(self, sample_item_instance_id, quantity):
        """更新後数量が0または負なら、値を含む理由でQuantityValidationExceptionを返す。"""
        with pytest.raises(QuantityValidationException) as exc_info:
            UpdateOperation(item_instance_id=sample_item_instance_id, new_quantity=quantity)
        assert f"Update operation: new_quantity must be positive, got {quantity}" in str(exc_info.value)


class TestCreateOperation:
    """CreateOperationのテスト"""

    @pytest.fixture
    def sample_item_spec(self):
        """テスト用のItemSpecを作成"""
        template_id = ItemSpecId(1)
        max_stack = MaxStackSize(64)
        return ItemSpec(
            item_spec_id=template_id,
            name="Test Item",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="A test item",
            max_stack_size=max_stack,
            equipment_type=EquipmentType.WEAPON,
        )

    @pytest.fixture
    def sample_durability(self):
        """テスト用のDurabilityを作成"""
        return Durability(max_value=100, current=100)

    @pytest.mark.parametrize("with_durability", [False, True], ids=["default-none", "durable-item"])
    def test_create_operation_retains_spec_quantity_and_durability(
        self, sample_item_spec, sample_durability, with_durability
    ):
        """生成操作は仕様と数量を保持し、耐久省略時はNone、耐久品では指定した耐久値を返す。"""
        if with_durability:
            item_spec = replace(sample_item_spec, max_stack_size=MaxStackSize(1), durability_max=100)
            operation = CreateOperation(item_spec=item_spec, quantity=1, durability=sample_durability)
            expected_quantity, expected_max_stack, expected_durability_max = 1, 1, 100
            expected_durability = sample_durability
        else:
            item_spec = sample_item_spec
            operation = CreateOperation(item_spec=item_spec, quantity=5)
            expected_quantity, expected_max_stack, expected_durability_max = 5, 64, None
            expected_durability = None

        assert operation.item_spec == item_spec
        assert operation.item_spec.max_stack_size.value == expected_max_stack
        assert operation.item_spec.durability_max == expected_durability_max
        assert operation.quantity == expected_quantity
        assert operation.durability == expected_durability

    def test_create_operation_immutable(self, sample_item_spec):
        """CreateOperationの不変性テスト"""
        operation = CreateOperation(item_spec=sample_item_spec, quantity=3)

        with pytest.raises(AttributeError):
            operation.quantity = 10

        with pytest.raises(AttributeError):
            operation.durability = Durability(max_value=50, current=50)

    @pytest.mark.parametrize("quantity", [0, -5])
    def test_create_operation_rejects_non_positive_quantity(self, sample_item_spec, quantity):
        """生成数量が0または負なら、値を含む理由でQuantityValidationExceptionを返す。"""
        with pytest.raises(QuantityValidationException) as exc_info:
            CreateOperation(item_spec=sample_item_spec, quantity=quantity)
        assert f"Create operation: quantity must be positive, got {quantity}" in str(exc_info.value)


class TestDeleteOperation:
    """DeleteOperationのテスト"""

    @pytest.fixture
    def sample_item_instance_id(self):
        """テスト用のItemInstanceIdを作成"""
        return ItemInstanceId(1)

    def test_delete_operation_immutable(self, sample_item_instance_id):
        """DeleteOperationの不変性テスト"""
        operation = DeleteOperation(item_instance_id=sample_item_instance_id)

        with pytest.raises(AttributeError):
            operation.item_instance_id = ItemInstanceId(999)


class TestMergePlan:
    """MergePlanのテスト"""

    @pytest.fixture
    def sample_operations(self):
        """テスト用の各種操作を作成"""
        # UpdateOperation
        update_op = UpdateOperation(item_instance_id=ItemInstanceId(1), new_quantity=10)

        # CreateOperation
        item_spec = ItemSpec(
            item_spec_id=ItemSpecId(2),
            name="New Item",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="A new item",
            max_stack_size=MaxStackSize(32),
        )
        create_op = CreateOperation(item_spec=item_spec, quantity=5)

        # DeleteOperation
        delete_op = DeleteOperation(item_instance_id=ItemInstanceId(3))

        return update_op, create_op, delete_op

    def test_merge_plan_immutable(self, sample_operations):
        """統合計画の3つの操作リスト属性は再代入できない。リスト内容の変更拒否は要求しない。"""
        update_op, create_op, delete_op = sample_operations

        plan = MergePlan(update_operations=[update_op], create_operations=[create_op], delete_operations=[delete_op])

        with pytest.raises(AttributeError):
            plan.update_operations = []

        with pytest.raises(AttributeError):
            plan.create_operations = []

        with pytest.raises(AttributeError):
            plan.delete_operations = []


class TestConsumedItem:
    """ConsumedItemのテスト"""

    @pytest.fixture
    def sample_item_instance_id(self):
        """テスト用のItemInstanceIdを作成"""
        return ItemInstanceId(1)

    def test_consumed_item_immutable(self, sample_item_instance_id):
        """ConsumedItemの不変性テスト"""
        consumed = ConsumedItem(item_instance_id=sample_item_instance_id, consumed_quantity=3, remaining_quantity=7)

        with pytest.raises(AttributeError):
            consumed.consumed_quantity = 10

        with pytest.raises(AttributeError):
            consumed.remaining_quantity = 5

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_consumed_item_rejects_non_positive_consumption(self, sample_item_instance_id, quantity):
        """残量が正しくても消費量が0または負なら正値制約で拒否する。"""
        with pytest.raises(QuantityValidationException) as exc_info:
            ConsumedItem(item_instance_id=sample_item_instance_id, consumed_quantity=quantity, remaining_quantity=10)
        assert "Consumed item: consumed_quantity must be positive" in str(exc_info.value)

    def test_invalid_remaining_quantity_negative(self, sample_item_instance_id):
        """無効なremaining_quantity（負数）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            ConsumedItem(item_instance_id=sample_item_instance_id, consumed_quantity=5, remaining_quantity=-1)
        assert "Consumed item: remaining_quantity must be non-negative" in str(exc_info.value)


class TestCraftingConsumptionPlan:
    """CraftingConsumptionPlanのテスト"""

    @pytest.fixture
    def sample_consumed_items(self):
        """テスト用のConsumedItemリストを作成"""
        return [
            ConsumedItem(item_instance_id=ItemInstanceId(1), consumed_quantity=5, remaining_quantity=10),
            ConsumedItem(item_instance_id=ItemInstanceId(2), consumed_quantity=8, remaining_quantity=0),
        ]

    @pytest.fixture
    def sample_operations(self):
        """テスト用の操作リストを作成"""
        return {
            "update_ops": [UpdateOperation(item_instance_id=ItemInstanceId(1), new_quantity=10)],
            "delete_ops": [DeleteOperation(item_instance_id=ItemInstanceId(2))],
        }

    def test_create_crafting_consumption_plan(self, sample_consumed_items, sample_operations):
        """消費記録と更新・削除対象を保持し、残量10ではなく消費5+8を合計して13を返す。"""
        plan = CraftingConsumptionPlan(
            consumed_items=sample_consumed_items,
            update_operations=sample_operations["update_ops"],
            delete_operations=sample_operations["delete_ops"],
        )

        assert len(plan.consumed_items) == 2
        assert len(plan.update_operations) == 1
        assert len(plan.delete_operations) == 1
        assert plan.total_consumed_quantity == 13  # 5 + 8

        assert sorted(
            (c.item_instance_id.value, c.consumed_quantity, c.remaining_quantity) for c in plan.consumed_items
        ) == [(1, 5, 10), (2, 8, 0)]
        assert sorted((op.item_instance_id.value, op.new_quantity) for op in plan.update_operations) == [(1, 10)]
        assert sorted(op.item_instance_id.value for op in plan.delete_operations) == [2]

    def test_crafting_consumption_plan_immutable(self, sample_consumed_items, sample_operations):
        """消費計画の消費・更新リスト属性は再代入できない。リスト内容の変更拒否は要求しない。"""
        plan = CraftingConsumptionPlan(
            consumed_items=sample_consumed_items,
            update_operations=sample_operations["update_ops"],
            delete_operations=sample_operations["delete_ops"],
        )

        with pytest.raises(AttributeError):
            plan.consumed_items = []

        with pytest.raises(AttributeError):
            plan.update_operations = []

    def test_empty_consumed_items(self, sample_operations):
        """空のconsumed_itemsのテスト"""
        plan = CraftingConsumptionPlan(
            consumed_items=[],
            update_operations=sample_operations["update_ops"],
            delete_operations=sample_operations["delete_ops"],
        )

        assert plan.total_consumed_quantity == 0
