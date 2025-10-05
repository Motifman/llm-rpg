import pytest
from src.domain.item.value_object.merge_plan import (
    MergePlan,
    UpdateOperation,
    CreateOperation,
    DeleteOperation,
    ConsumedItem,
    CraftingConsumptionPlan
)
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.value_object.item_spec import ItemSpec
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.max_stack_size import MaxStackSize
from src.domain.item.value_object.durability import Durability
from src.domain.item.enum.item_enum import ItemType, Rarity
from src.domain.item.exception import QuantityValidationException


class TestUpdateOperation:
    """UpdateOperationのテスト"""

    @pytest.fixture
    def sample_item_instance_id(self):
        """テスト用のItemInstanceIdを作成"""
        return ItemInstanceId(1)

    def test_create_update_operation(self, sample_item_instance_id):
        """UpdateOperationの作成テスト"""
        operation = UpdateOperation(
            item_instance_id=sample_item_instance_id,
            new_quantity=10
        )
        assert operation.item_instance_id == sample_item_instance_id
        assert operation.new_quantity == 10

    def test_update_operation_immutable(self, sample_item_instance_id):
        """UpdateOperationの不変性テスト"""
        operation = UpdateOperation(
            item_instance_id=sample_item_instance_id,
            new_quantity=5
        )

        with pytest.raises(AttributeError):
            operation.new_quantity = 20

        with pytest.raises(AttributeError):
            operation.item_instance_id = ItemInstanceId(999)

    def test_invalid_new_quantity_zero(self, sample_item_instance_id):
        """無効なnew_quantity（0）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            UpdateOperation(
                item_instance_id=sample_item_instance_id,
                new_quantity=0
            )
        assert exc_info.value.quantity == 0
        assert "new_quantity must be positive" in str(exc_info.value)

    def test_invalid_new_quantity_negative(self, sample_item_instance_id):
        """無効なnew_quantity（負の値）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            UpdateOperation(
                item_instance_id=sample_item_instance_id,
                new_quantity=-1
            )
        assert exc_info.value.quantity == -1
        assert "new_quantity must be positive" in str(exc_info.value)


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
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
            description="A test item",
            max_stack_size=max_stack
        )

    @pytest.fixture
    def sample_durability(self):
        """テスト用のDurabilityを作成"""
        return Durability(max_value=100, current=100)

    def test_create_operation_without_durability(self, sample_item_spec):
        """耐久度なしのCreateOperation作成テスト"""
        operation = CreateOperation(
            item_spec=sample_item_spec,
            quantity=5
        )
        assert operation.item_spec == sample_item_spec
        assert operation.quantity == 5
        assert operation.durability is None

    def test_create_operation_with_durability(self, sample_item_spec, sample_durability):
        """耐久度付きのCreateOperation作成テスト"""
        operation = CreateOperation(
            item_spec=sample_item_spec,
            quantity=1,
            durability=sample_durability
        )
        assert operation.item_spec == sample_item_spec
        assert operation.quantity == 1
        assert operation.durability == sample_durability

    def test_create_operation_immutable(self, sample_item_spec):
        """CreateOperationの不変性テスト"""
        operation = CreateOperation(
            item_spec=sample_item_spec,
            quantity=3
        )

        with pytest.raises(AttributeError):
            operation.quantity = 10

        with pytest.raises(AttributeError):
            operation.durability = Durability(max_value=50, current=50)

    def test_invalid_quantity_zero(self, sample_item_spec):
        """無効なquantity（0）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            CreateOperation(
                item_spec=sample_item_spec,
                quantity=0
            )
        assert exc_info.value.quantity == 0
        assert "quantity must be positive" in str(exc_info.value)

    def test_invalid_quantity_negative(self, sample_item_spec):
        """無効なquantity（負の値）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            CreateOperation(
                item_spec=sample_item_spec,
                quantity=-5
            )
        assert exc_info.value.quantity == -5
        assert "quantity must be positive" in str(exc_info.value)


class TestDeleteOperation:
    """DeleteOperationのテスト"""

    @pytest.fixture
    def sample_item_instance_id(self):
        """テスト用のItemInstanceIdを作成"""
        return ItemInstanceId(1)

    def test_create_delete_operation(self, sample_item_instance_id):
        """DeleteOperationの作成テスト"""
        operation = DeleteOperation(
            item_instance_id=sample_item_instance_id
        )
        assert operation.item_instance_id == sample_item_instance_id

    def test_delete_operation_immutable(self, sample_item_instance_id):
        """DeleteOperationの不変性テスト"""
        operation = DeleteOperation(
            item_instance_id=sample_item_instance_id
        )

        with pytest.raises(AttributeError):
            operation.item_instance_id = ItemInstanceId(999)


class TestMergePlan:
    """MergePlanのテスト"""

    @pytest.fixture
    def sample_operations(self):
        """テスト用の各種操作を作成"""
        # UpdateOperation
        update_op = UpdateOperation(
            item_instance_id=ItemInstanceId(1),
            new_quantity=10
        )

        # CreateOperation
        item_spec = ItemSpec(
            item_spec_id=ItemSpecId(2),
            name="New Item",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="A new item",
            max_stack_size=MaxStackSize(32)
        )
        create_op = CreateOperation(
            item_spec=item_spec,
            quantity=5
        )

        # DeleteOperation
        delete_op = DeleteOperation(
            item_instance_id=ItemInstanceId(3)
        )

        return update_op, create_op, delete_op

    def test_create_merge_plan_with_operations(self, sample_operations):
        """操作付きのMergePlan作成テスト"""
        update_op, create_op, delete_op = sample_operations

        plan = MergePlan(
            update_operations=[update_op],
            create_operations=[create_op],
            delete_operations=[delete_op]
        )

        assert plan.update_operations == [update_op]
        assert plan.create_operations == [create_op]
        assert plan.delete_operations == [delete_op]

    def test_create_empty_merge_plan(self):
        """空のMergePlan作成テスト"""
        plan = MergePlan(
            update_operations=[],
            create_operations=[],
            delete_operations=[]
        )

        assert plan.update_operations == []
        assert plan.create_operations == []
        assert plan.delete_operations == []

    def test_merge_plan_immutable(self, sample_operations):
        """MergePlanの不変性テスト"""
        update_op, create_op, delete_op = sample_operations

        plan = MergePlan(
            update_operations=[update_op],
            create_operations=[create_op],
            delete_operations=[delete_op]
        )

        with pytest.raises(AttributeError):
            plan.update_operations = []

        with pytest.raises(AttributeError):
            plan.create_operations = []

        with pytest.raises(AttributeError):
            plan.delete_operations = []

    def test_merge_plan_with_multiple_operations(self):
        """複数操作のMergePlanテスト"""
        update_ops = [
            UpdateOperation(ItemInstanceId(1), 10),
            UpdateOperation(ItemInstanceId(2), 20)
        ]

        create_ops = [
            CreateOperation(
                ItemSpec(
                    ItemSpecId(10),
                    "Item A",
                    ItemType.WEAPON,
                    Rarity.COMMON,
                    "Item A desc",
                    MaxStackSize(64)
                ),
                5
            ),
            CreateOperation(
                ItemSpec(
                    ItemSpecId(11),
                    "Item B",
                    ItemType.CONSUMABLE,
                    Rarity.UNCOMMON,
                    "Item B desc",
                    MaxStackSize(32)
                ),
                3
            )
        ]

        delete_ops = [
            DeleteOperation(ItemInstanceId(100)),
            DeleteOperation(ItemInstanceId(101)),
            DeleteOperation(ItemInstanceId(102))
        ]

        plan = MergePlan(
            update_operations=update_ops,
            create_operations=create_ops,
            delete_operations=delete_ops
        )

        assert len(plan.update_operations) == 2
        assert len(plan.create_operations) == 2
        assert len(plan.delete_operations) == 3


class TestConsumedItem:
    """ConsumedItemのテスト"""

    @pytest.fixture
    def sample_item_instance_id(self):
        """テスト用のItemInstanceIdを作成"""
        return ItemInstanceId(1)

    def test_create_consumed_item(self, sample_item_instance_id):
        """ConsumedItemの作成テスト"""
        consumed = ConsumedItem(
            item_instance_id=sample_item_instance_id,
            consumed_quantity=5,
            remaining_quantity=10
        )
        assert consumed.item_instance_id == sample_item_instance_id
        assert consumed.consumed_quantity == 5
        assert consumed.remaining_quantity == 10

    def test_consumed_item_immutable(self, sample_item_instance_id):
        """ConsumedItemの不変性テスト"""
        consumed = ConsumedItem(
            item_instance_id=sample_item_instance_id,
            consumed_quantity=3,
            remaining_quantity=7
        )

        with pytest.raises(AttributeError):
            consumed.consumed_quantity = 10

        with pytest.raises(AttributeError):
            consumed.remaining_quantity = 5

    def test_invalid_consumed_quantity_zero(self, sample_item_instance_id):
        """無効なconsumed_quantity（0）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            ConsumedItem(
                item_instance_id=sample_item_instance_id,
                consumed_quantity=0,
                remaining_quantity=10
            )
        assert "consumed_quantity must be positive" in str(exc_info.value)

    def test_invalid_consumed_quantity_negative(self, sample_item_instance_id):
        """無効なconsumed_quantity（負数）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            ConsumedItem(
                item_instance_id=sample_item_instance_id,
                consumed_quantity=-1,
                remaining_quantity=10
            )
        assert "consumed_quantity must be positive" in str(exc_info.value)

    def test_invalid_remaining_quantity_negative(self, sample_item_instance_id):
        """無効なremaining_quantity（負数）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            ConsumedItem(
                item_instance_id=sample_item_instance_id,
                consumed_quantity=5,
                remaining_quantity=-1
            )
        assert "remaining_quantity must be non-negative" in str(exc_info.value)


class TestCraftingConsumptionPlan:
    """CraftingConsumptionPlanのテスト"""

    @pytest.fixture
    def sample_consumed_items(self):
        """テスト用のConsumedItemリストを作成"""
        return [
            ConsumedItem(
                item_instance_id=ItemInstanceId(1),
                consumed_quantity=5,
                remaining_quantity=10
            ),
            ConsumedItem(
                item_instance_id=ItemInstanceId(2),
                consumed_quantity=8,
                remaining_quantity=0
            )
        ]

    @pytest.fixture
    def sample_operations(self):
        """テスト用の操作リストを作成"""
        return {
            'update_ops': [
                UpdateOperation(item_instance_id=ItemInstanceId(1), new_quantity=10)
            ],
            'delete_ops': [
                DeleteOperation(item_instance_id=ItemInstanceId(2))
            ]
        }

    def test_create_crafting_consumption_plan(self, sample_consumed_items, sample_operations):
        """CraftingConsumptionPlanの作成テスト"""
        plan = CraftingConsumptionPlan(
            consumed_items=sample_consumed_items,
            update_operations=sample_operations['update_ops'],
            delete_operations=sample_operations['delete_ops']
        )

        assert len(plan.consumed_items) == 2
        assert len(plan.update_operations) == 1
        assert len(plan.delete_operations) == 1
        assert plan.total_consumed_quantity == 13  # 5 + 8

    def test_crafting_consumption_plan_immutable(self, sample_consumed_items, sample_operations):
        """CraftingConsumptionPlanの不変性テスト"""
        plan = CraftingConsumptionPlan(
            consumed_items=sample_consumed_items,
            update_operations=sample_operations['update_ops'],
            delete_operations=sample_operations['delete_ops']
        )

        with pytest.raises(AttributeError):
            plan.consumed_items = []

        with pytest.raises(AttributeError):
            plan.update_operations = []

    def test_empty_consumed_items(self, sample_operations):
        """空のconsumed_itemsのテスト"""
        plan = CraftingConsumptionPlan(
            consumed_items=[],
            update_operations=sample_operations['update_ops'],
            delete_operations=sample_operations['delete_ops']
        )

        assert plan.total_consumed_quantity == 0
