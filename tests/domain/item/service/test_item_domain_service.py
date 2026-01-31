import pytest
from ai_rpg_world.domain.item.service.item_domain_service import ItemStackingDomainService
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from ai_rpg_world.domain.item.value_object.merge_plan import (
    MergePlan, UpdateOperation, CreateOperation, DeleteOperation,
    CraftingConsumptionPlan, ConsumedItem
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.domain.item.value_object.recipe_ingredient import RecipeIngredient
from ai_rpg_world.domain.item.value_object.recipe_result import RecipeResult
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from ai_rpg_world.domain.item.exception import InsufficientIngredientsException


class TestItemStackingDomainServiceCrafting:
    """ItemStackingDomainServiceのクラフト関連機能テスト"""

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
        """正常系：各材料が単一のアイテムでまかなえる場合"""
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

    def test_plan_crafting_consumption_success_multiple_items_same_spec(
        self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone
    ):
        """正常系：同じスペックの材料が複数のアイテムに分散している場合"""
        # 木材を3つのアイテムに分散（3, 2, 10個）
        wood_item1 = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=sample_item_spec_wood,
            quantity=3
        )
        wood_item2 = ItemAggregate.create(
            item_instance_id=ItemInstanceId(2),
            item_spec=sample_item_spec_wood,
            quantity=2
        )
        wood_item3 = ItemAggregate.create(
            item_instance_id=ItemInstanceId(3),
            item_spec=sample_item_spec_wood,
            quantity=10
        )
        stone_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(4),
            item_spec=sample_item_spec_stone,
            quantity=5  # 必要:1, 残り:4
        )
        available_items = [wood_item1, wood_item2, wood_item3, stone_item]

        # 消費計画を作成
        plan = ItemStackingDomainService.plan_crafting_consumption(
            sample_recipe, available_items
        )

        # 検証
        assert isinstance(plan, CraftingConsumptionPlan)
        assert len(plan.consumed_items) == 2  # wood_item1とstone_itemから消費
        assert len(plan.update_operations) == 2  # 両方とも部分消費
        assert len(plan.delete_operations) == 0  # 完全に消費されるアイテムなし

        # 消費アイテムの詳細検証
        consumed_ids = {c.item_instance_id.value for c in plan.consumed_items}
        assert consumed_ids == {1, 4}  # wood_item1とstone_itemから消費

        # wood_item1: 3個持っていて2個消費、残り1個
        wood_consumed = next(c for c in plan.consumed_items if c.item_instance_id == ItemInstanceId(1))
        assert wood_consumed.consumed_quantity == 2
        assert wood_consumed.remaining_quantity == 1

        # stone_item: 5個持っていて1個消費、残り4個
        stone_consumed = next(c for c in plan.consumed_items if c.item_instance_id == ItemInstanceId(4))
        assert stone_consumed.consumed_quantity == 1
        assert stone_consumed.remaining_quantity == 4

    def test_plan_crafting_consumption_complete_consumption(
        self, sample_item_spec_wood, sample_item_spec_stone, sample_item_spec_sword
    ):
        """正常系：アイテムが完全に消費される場合"""
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

    def test_plan_crafting_consumption_insufficient_ingredients_missing_spec(
        self, sample_recipe, sample_item_spec_wood
    ):
        """異常系：必要な材料スペックが存在しない場合"""
        # 石アイテムのみ（木材なし）
        stone_item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(1),
            item_spec=sample_item_spec_wood,  # 石ではなく木材として作成（故意のミス）
            quantity=10
        )
        available_items = [stone_item]

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

    def test_plan_merge_same_spec_items_exceed_stack_limit(self, sample_item_spec_stackable):
        """同じスペックのアイテムがスタック上限を超えるマージ計画テスト"""
        # スタック上限は64
        items = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(111),
                item_spec=sample_item_spec_stackable,
                quantity=30
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(112),
                item_spec=sample_item_spec_stackable,
                quantity=40
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(113),
                item_spec=sample_item_spec_stackable,
                quantity=25
            )
        ]

        plan = ItemStackingDomainService.plan_merge(items)

        assert isinstance(plan, MergePlan)
        assert len(plan.update_operations) == 1  # 最初のアイテムを64個に更新
        assert len(plan.create_operations) == 1  # 残りの31個分を新規作成
        assert len(plan.delete_operations) == 2  # 残りの2つのアイテムを削除

        # 更新操作の検証
        update_op = plan.update_operations[0]
        assert update_op.item_instance_id == ItemInstanceId(111)
        assert update_op.new_quantity == 64

        # 作成操作の検証
        create_op = plan.create_operations[0]
        assert create_op.item_spec == sample_item_spec_stackable
        assert create_op.quantity == 31  # 95 - 64 = 31

        # 削除操作の検証
        delete_ids = {op.item_instance_id for op in plan.delete_operations}
        assert delete_ids == {ItemInstanceId(112), ItemInstanceId(113)}

    def test_plan_merge_multiple_specs(self, sample_item_spec_stackable, sample_item_spec_non_stackable):
        """複数の異なるスペックのアイテムのマージ計画テスト"""
        items = [
            # スタック可能なアイテム2つ
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(114),
                item_spec=sample_item_spec_stackable,
                quantity=20
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(115),
                item_spec=sample_item_spec_stackable,
                quantity=30
            ),
            # スタック不可能なアイテム1つ（耐久度付き）
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(116),
                item_spec=sample_item_spec_non_stackable,
                quantity=1
            )
        ]

        plan = ItemStackingDomainService.plan_merge(items)

        assert isinstance(plan, MergePlan)
        # スタック可能なスペックについてのみマージ操作
        assert len(plan.update_operations) == 1
        assert len(plan.create_operations) == 0
        assert len(plan.delete_operations) == 1

        # 更新操作（スタック可能なアイテム）
        update_op = plan.update_operations[0]
        assert update_op.item_instance_id == ItemInstanceId(114)
        assert update_op.new_quantity == 50

        # 削除操作（スタック可能な2番目のアイテム）
        delete_op = plan.delete_operations[0]
        assert delete_op.item_instance_id == ItemInstanceId(115)

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
