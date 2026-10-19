import pytest

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.exception import InsufficientIngredientsException
from ai_rpg_world.domain.item.service.item_domain_service import ItemStackingDomainService
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.value_object.merge_plan import (
    CraftingConsumptionPlan,
    MergePlan,
)
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.domain.item.value_object.recipe_ingredient import RecipeIngredient
from ai_rpg_world.domain.item.value_object.recipe_result import RecipeResult


class TestItemStackingDomainServiceCrafting:
    """材料の実体ごとの消費量と、部分消費の更新・全消費の削除計画を保証する。"""

    @pytest.fixture
    def sample_item_spec_wood(self):
        """テスト用の木材アイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(1),
            name="Wood",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="A piece of wood",
            max_stack_size=MaxStackSize(64)
        )

    @pytest.fixture
    def sample_item_spec_stone(self):
        """テスト用の石アイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(2),
            name="Stone",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="A piece of stone",
            max_stack_size=MaxStackSize(64)
        )

    @pytest.fixture
    def sample_item_spec_sword(self):
        """テスト用の剣アイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(3),
            name="Wooden Sword",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="A wooden sword",
            max_stack_size=MaxStackSize(1),
            equipment_type=EquipmentType.WEAPON
        )

    @pytest.fixture
    def sample_recipe(self, sample_item_spec_wood, sample_item_spec_stone, sample_item_spec_sword):
        """テスト用のレシピを作成"""
        return RecipeAggregate(
            recipe_id=RecipeId(1),
            name="Wooden Sword Recipe",
            description="Craft a wooden sword using wood and stone",
            ingredients=[
                RecipeIngredient(
                    item_spec_id=sample_item_spec_wood.item_spec_id,
                    quantity=2
                ),
                RecipeIngredient(
                    item_spec_id=sample_item_spec_stone.item_spec_id,
                    quantity=1
                )
            ],
            result=RecipeResult(
                item_spec_id=sample_item_spec_sword.item_spec_id,
                quantity=1
            )
        )

    def test_plan_crafting_consumption_success_single_item_each(
        self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone
    ):
        """木材5・石3から要求2・1を消費する計画を返し、元の数量は変更しない。"""
        # 利用可能なアイテムを作成
        wood_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=sample_item_spec_wood,
            quantity=5  # 必要:2, 残り:3
        )
        stone_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(2),
            item_spec=sample_item_spec_stone,
            quantity=3  # 必要:1, 残り:2
        )
        available_items = [wood_item, stone_item]

        # 消費計画を作成
        plan = ItemStackingDomainService.plan_crafting_consumption(
            sample_recipe, available_items
        )

        # 検証
        assert isinstance(plan, CraftingConsumptionPlan)
        assert len(plan.consumed_items) == 2
        assert len(plan.update_operations) == 2  # 両方とも部分消費
        assert len(plan.delete_operations) == 0  # 完全に消費されるアイテムなし

        # 消費アイテムの詳細検証
        wood_consumed = next(c for c in plan.consumed_items if c.item_instance_id == ItemInstanceId(1))
        assert wood_consumed.consumed_quantity == 2
        assert wood_consumed.remaining_quantity == 3

        stone_consumed = next(c for c in plan.consumed_items if c.item_instance_id == ItemInstanceId(2))
        assert stone_consumed.consumed_quantity == 1
        assert stone_consumed.remaining_quantity == 2

        assert sorted((op.item_instance_id.value, op.new_quantity) for op in plan.update_operations) == [(1, 3), (2, 2)]
        assert plan.total_consumed_quantity == 3
        assert [item.quantity for item in available_items] == [5, 3]

    @pytest.mark.parametrize(
        "wood_quantities, expected_consumed, expected_updates, expected_deletes",
        [
            ((3, 2, 10), [(1, 2, 1), (4, 1, 4)], [(1, 1), (4, 4)], []),
            ((1, 2, 10), [(1, 1, 0), (2, 1, 1), (4, 1, 4)], [(2, 1), (4, 4)], [1]),
        ],
        ids=["first-stack-suffices", "consumption-crosses-stacks"],
    )
    def test_plan_crafting_consumption_success_multiple_items_same_spec(
        self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone,
        wood_quantities, expected_consumed, expected_updates, expected_deletes,
    ):
        """要求2を木材の先頭から消費し、実体を跨ぐ場合も余剰実体を残して更新と削除を分ける。"""
        available_items = [
            ItemAggregate.create(ItemInstanceId(index), sample_item_spec_wood, quantity=quantity)
            for index, quantity in enumerate(wood_quantities, start=1)
        ]
        available_items.append(ItemAggregate.create(ItemInstanceId(4), sample_item_spec_stone, quantity=5))

        plan = ItemStackingDomainService.plan_crafting_consumption(sample_recipe, available_items)

        assert isinstance(plan, CraftingConsumptionPlan)
        assert sorted((c.item_instance_id.value, c.consumed_quantity, c.remaining_quantity) for c in plan.consumed_items) == expected_consumed
        assert sorted((op.item_instance_id.value, op.new_quantity) for op in plan.update_operations) == expected_updates
        assert sorted(op.item_instance_id.value for op in plan.delete_operations) == expected_deletes
        assert plan.total_consumed_quantity == 3
        assert [item.quantity for item in available_items] == [*wood_quantities, 5]

    def test_plan_crafting_consumption_complete_consumption(
        self, sample_item_spec_wood, sample_item_spec_stone, sample_item_spec_sword
    ):
        """要求どおりの木材2・石1は残量0の消費記録と削除計画を返し、入力は変更しない。"""
        # 必要な分だけ持っているアイテム
        wood_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=sample_item_spec_wood,
            quantity=2  # 必要:2, 残り:0
        )
        stone_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(2),
            item_spec=sample_item_spec_stone,
            quantity=1  # 必要:1, 残り:0
        )
        available_items = [wood_item, stone_item]

        recipe = RecipeAggregate(
            recipe_id=RecipeId(1),
            name="Test Recipe",
            description="Test",
            ingredients=[
                RecipeIngredient(
                    item_spec_id=sample_item_spec_wood.item_spec_id,
                    quantity=2
                ),
                RecipeIngredient(
                    item_spec_id=sample_item_spec_stone.item_spec_id,
                    quantity=1
                )
            ],
            result=RecipeResult(
                item_spec_id=sample_item_spec_sword.item_spec_id,
                quantity=1
            )
        )

        # 消費計画を作成
        plan = ItemStackingDomainService.plan_crafting_consumption(
            recipe, available_items
        )

        # 検証
        assert len(plan.consumed_items) == 2
        assert len(plan.update_operations) == 0  # 部分消費なし
        assert len(plan.delete_operations) == 2  # 両方とも完全に消費

        # 削除操作の検証
        delete_ids = {op.item_instance_id for op in plan.delete_operations}
        assert delete_ids == {ItemInstanceId(1), ItemInstanceId(2)}

        assert sorted((c.item_instance_id.value, c.consumed_quantity, c.remaining_quantity) for c in plan.consumed_items) == [(1, 2, 0), (2, 1, 0)]
        assert [item.quantity for item in available_items] == [2, 1]

    def test_plan_crafting_consumption_insufficient_ingredients_missing_spec(
        self, sample_recipe, sample_item_spec_wood
    ):
        """異常系：必要な材料スペックが存在しない場合"""
        # 木材だけがあり、必要な石がない
        wood_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=sample_item_spec_wood,
            quantity=10
        )
        available_items = [wood_item]

        with pytest.raises(InsufficientIngredientsException) as exc_info:
            ItemStackingDomainService.plan_crafting_consumption(
                sample_recipe, available_items
            )

        assert "Recipe 1:" in str(exc_info.value)
        assert "missing ingredient" in str(exc_info.value)

    def test_plan_crafting_consumption_insufficient_quantity(
        self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone
    ):
        """異常系：材料の数量が不足している場合"""
        # 木材が1個しかない（必要:2）
        wood_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=sample_item_spec_wood,
            quantity=1  # 不足
        )
        stone_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(2),
            item_spec=sample_item_spec_stone,
            quantity=10  # 十分
        )
        available_items = [wood_item, stone_item]

        with pytest.raises(InsufficientIngredientsException) as exc_info:
            ItemStackingDomainService.plan_crafting_consumption(
                sample_recipe, available_items
            )

        assert "Recipe 1:" in str(exc_info.value)
        assert "insufficient quantity for ingredient" in str(exc_info.value)

    def test_plan_crafting_consumption_empty_available_items(self, sample_recipe):
        """異常系：利用可能なアイテムが空の場合"""
        with pytest.raises(InsufficientIngredientsException):
            ItemStackingDomainService.plan_crafting_consumption(
                sample_recipe, []
            )

    def test_plan_crafting_consumption_minimal_ingredients_recipe(
        self, sample_item_spec_wood, sample_item_spec_sword
    ):
        """正常系：最小限の材料でクラフトする場合"""
        # 1個の材料のみ必要なレシピ
        recipe = RecipeAggregate(
            recipe_id=RecipeId(1),
            name="Simple Recipe",
            description="Simple crafting",
            ingredients=[
                RecipeIngredient(
                    item_spec_id=sample_item_spec_wood.item_spec_id,
                    quantity=1
                )
            ],
            result=RecipeResult(
                item_spec_id=sample_item_spec_sword.item_spec_id,
                quantity=1
            )
        )

        # ちょうど1個のアイテム
        wood_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=sample_item_spec_wood,
            quantity=1  # 必要:1, 残り:0
        )

        plan = ItemStackingDomainService.plan_crafting_consumption(
            recipe, [wood_item]
        )

        assert len(plan.consumed_items) == 1
        assert len(plan.update_operations) == 0  # 部分消費なし
        assert len(plan.delete_operations) == 1  # 完全に消費
        assert plan.total_consumed_quantity == 1

        # 削除操作の検証
        assert plan.delete_operations[0].item_instance_id == ItemInstanceId(1)


class TestItemStackingDomainServiceStacking:
    """ItemStackingDomainServiceのスタッキング関連機能テスト"""

    @pytest.fixture
    def sample_item_spec_stackable(self):
        """スタック可能なアイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(10),
            name="Stackable Item",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="A stackable item",
            max_stack_size=MaxStackSize(64)
        )

    @pytest.fixture
    def sample_item_spec_non_stackable(self):
        """スタック不可能なアイテム仕様を作成（耐久度付き）"""
        return ItemSpec(
            item_spec_id=ItemSpecId(11),
            name="Non-Stackable Item",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.UNCOMMON,
            description="A non-stackable item",
            max_stack_size=MaxStackSize(1),
            durability_max=100,
            equipment_type=EquipmentType.WEAPON
        )

    def test_calculate_max_stack_quantity_single_item(self, sample_item_spec_stackable):
        """単一アイテムのスタック数量計算テスト"""
        base_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(100),
            item_spec=sample_item_spec_stackable,
            quantity=10
        )
        additional_items = []

        total_quantity, stackable_items = ItemStackingDomainService.calculate_max_stack_quantity(
            base_item, additional_items
        )

        assert total_quantity == 10
        assert len(stackable_items) == 0

    def test_calculate_max_stack_quantity_with_stackable_items(self, sample_item_spec_stackable):
        """スタック可能な追加アイテムがある場合の計算テスト"""
        base_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(101),
            item_spec=sample_item_spec_stackable,
            quantity=20
        )

        additional_items = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(102),
                item_spec=sample_item_spec_stackable,
                quantity=30
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(103),
                item_spec=sample_item_spec_stackable,
                quantity=40
            )
        ]

        total_quantity, stackable_items = ItemStackingDomainService.calculate_max_stack_quantity(
            base_item, additional_items
        )

        assert total_quantity == 90  # 20 + 30 + 40
        assert len(stackable_items) == 2
        assert stackable_items[0].item_instance_id == ItemInstanceId(102)
        assert stackable_items[1].item_instance_id == ItemInstanceId(103)

    def test_calculate_max_stack_quantity_with_non_stackable_items(self, sample_item_spec_stackable, sample_item_spec_non_stackable):
        """スタック不可能なアイテムが混在する場合の計算テスト"""
        base_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(104),
            item_spec=sample_item_spec_stackable,
            quantity=10
        )

        additional_items = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(105),
                item_spec=sample_item_spec_stackable,
                quantity=20
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(106),
                item_spec=sample_item_spec_non_stackable,
                quantity=1
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(107),
                item_spec=sample_item_spec_stackable,
                quantity=15
            )
        ]

        total_quantity, stackable_items = ItemStackingDomainService.calculate_max_stack_quantity(
            base_item, additional_items
        )

        assert total_quantity == 45  # 10 + 20 + 15 (非スタック可能アイテムは除外)
        assert len(stackable_items) == 2
        assert stackable_items[0].item_instance_id == ItemInstanceId(105)
        assert stackable_items[1].item_instance_id == ItemInstanceId(107)

    def test_plan_merge_empty_items(self):
        """空のアイテムリストのマージ計画テスト"""
        plan = ItemStackingDomainService.plan_merge([])

        assert isinstance(plan, MergePlan)
        assert len(plan.update_operations) == 0
        assert len(plan.create_operations) == 0
        assert len(plan.delete_operations) == 0

    def test_plan_merge_single_item(self, sample_item_spec_stackable):
        """単一アイテムのマージ計画テスト"""
        items = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(108),
                item_spec=sample_item_spec_stackable,
                quantity=10
            )
        ]

        plan = ItemStackingDomainService.plan_merge(items)

        assert isinstance(plan, MergePlan)
        assert len(plan.update_operations) == 0  # 変更なし
        assert len(plan.create_operations) == 0
        assert len(plan.delete_operations) == 0

    def test_plan_merge_same_spec_items_within_stack_limit(self, sample_item_spec_stackable):
        """同じスペックのアイテムがスタック上限以内のマージ計画テスト"""
        items = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(109),
                item_spec=sample_item_spec_stackable,
                quantity=20
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(110),
                item_spec=sample_item_spec_stackable,
                quantity=30
            )
        ]

        plan = ItemStackingDomainService.plan_merge(items)

        assert isinstance(plan, MergePlan)
        assert len(plan.update_operations) == 1  # 最初のアイテムを50個に更新
        assert len(plan.create_operations) == 0  # スタック上限内なので作成不要
        assert len(plan.delete_operations) == 1  # 2番目のアイテムを削除

        # 更新操作の検証
        update_op = plan.update_operations[0]
        assert update_op.item_instance_id == ItemInstanceId(109)
        assert update_op.new_quantity == 50

        # 削除操作の検証
        delete_op = plan.delete_operations[0]
        assert delete_op.item_instance_id == ItemInstanceId(110)

    @pytest.mark.parametrize(
        "quantities, expected_created, expected_deleted",
        [
            ((30, 40, 25), [31], [112, 113]),
            ((64, 32, 32, 31), [64, 31], [112, 113, 114]),
        ],
        ids=["one-extra-stack", "two-extra-stacks-three-deletions"],
    )
    def test_plan_merge_same_spec_items_exceed_stack_limit(
        self, sample_item_spec_stackable, quantities, expected_created, expected_deleted,
    ):
        """合計95と159を上限64で分割し、先頭IDを残して余剰実体すべてを削除する計画を返す。"""
        items = [
            ItemAggregate.create(ItemInstanceId(index), sample_item_spec_stackable, quantity=quantity)
            for index, quantity in enumerate(quantities, start=111)
        ]

        plan = ItemStackingDomainService.plan_merge(items)

        assert isinstance(plan, MergePlan)
        assert sorted((op.item_instance_id.value, op.new_quantity) for op in plan.update_operations) == [(111, 64)]
        assert sorted(op.quantity for op in plan.create_operations) == sorted(expected_created)
        assert [op.item_spec.item_spec_id.value for op in plan.create_operations] == [10] * len(expected_created)
        assert [op.item_spec.max_stack_size.value for op in plan.create_operations] == [64] * len(expected_created)
        assert all(op.item_spec.durability_max is None and op.durability is None for op in plan.create_operations)
        assert sorted(op.item_instance_id.value for op in plan.delete_operations) == expected_deleted
        assert [item.quantity for item in items] == list(quantities)

    @pytest.mark.parametrize(
        "first_quantities, second_quantities, expected_updates, expected_created, expected_deleted",
        [
            ((20, 30), (), [(114, 50)], [], [115]),
            ((50, 30), (20, 20), [(114, 64), (119, 32)], [(10, 64, 16), (12, 32, 8)], [115, 120]),
        ],
        ids=["stackable-and-durable", "two-stackable-specs-and-durable"],
    )
    def test_plan_merge_multiple_specs(
        self, sample_item_spec_stackable, sample_item_spec_non_stackable,
        first_quantities, second_quantities, expected_updates, expected_created, expected_deleted,
    ):
        """耐久品を除外し、同名でも仕様IDが異なる通常品はそれぞれの上限で別々に統合する。"""
        second_spec = ItemSpec(
            item_spec_id=ItemSpecId(12),
            name=sample_item_spec_stackable.name,
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="Another stackable specification",
            max_stack_size=MaxStackSize(32),
        )
        items = [
            ItemAggregate.create(ItemInstanceId(index), sample_item_spec_stackable, quantity=quantity)
            for index, quantity in enumerate(first_quantities, start=114)
        ]
        items.extend(
            ItemAggregate.create(ItemInstanceId(index), second_spec, quantity=quantity)
            for index, quantity in enumerate(second_quantities, start=119)
        )
        items.append(ItemAggregate.create(ItemInstanceId(116), sample_item_spec_non_stackable, quantity=1))

        plan = ItemStackingDomainService.plan_merge(items)

        assert isinstance(plan, MergePlan)
        assert sorted((op.item_instance_id.value, op.new_quantity) for op in plan.update_operations) == expected_updates
        assert sorted((op.item_spec.item_spec_id.value, op.item_spec.max_stack_size.value, op.quantity) for op in plan.create_operations) == expected_created
        assert all(op.item_spec.durability_max is None and op.durability is None for op in plan.create_operations)
        assert sorted(op.item_instance_id.value for op in plan.delete_operations) == expected_deleted
        assert [item.quantity for item in items] == [*first_quantities, *second_quantities, 1]

        # スタック不可能なアイテム（耐久度付き）はマージ対象外なので操作なし

    def test_plan_merge_non_stackable_items_unchanged(self, sample_item_spec_non_stackable):
        """スタック不可能なアイテムはマージ操作の対象外になるテスト"""
        items = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(117),
                item_spec=sample_item_spec_non_stackable,
                quantity=1
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(118),
                item_spec=sample_item_spec_non_stackable,
                quantity=1
            )
        ]

        plan = ItemStackingDomainService.plan_merge(items)

        assert isinstance(plan, MergePlan)
        # 耐久度付きアイテムはスタック不可なのでマージ操作なし
        assert len(plan.update_operations) == 0
        assert len(plan.create_operations) == 0
        assert len(plan.delete_operations) == 0
