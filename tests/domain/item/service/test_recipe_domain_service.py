import pytest
from src.domain.item.service.recipe_domain_service import RecipeDomainService
from src.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from src.domain.item.aggregate.item_aggregate import ItemAggregate
from src.domain.item.value_object.recipe_id import RecipeId
from src.domain.item.value_object.recipe_ingredient import RecipeIngredient
from src.domain.item.value_object.recipe_result import RecipeResult
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.value_object.item_spec import ItemSpec
from src.domain.item.value_object.max_stack_size import MaxStackSize
from src.domain.item.enum.item_enum import ItemType, Rarity


class TestRecipeDomainService:
    """RecipeDomainServiceのテスト"""

    @pytest.fixture
    def sample_item_spec_wood(self):
        """木材アイテム仕様を作成"""
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
        """石アイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(2),
            name="Stone",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="A piece of stone",
            max_stack_size=MaxStackSize(64)
        )

    @pytest.fixture
    def sample_item_spec_iron(self):
        """鉄アイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(3),
            name="Iron",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.UNCOMMON,
            description="A piece of iron",
            max_stack_size=MaxStackSize(64)
        )

    @pytest.fixture
    def sample_item_spec_sword(self):
        """剣アイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(4),
            name="Wooden Sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
            description="A wooden sword",
            max_stack_size=MaxStackSize(1)
        )

    @pytest.fixture
    def sample_item_spec_pickaxe(self):
        """つるはしアイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(5),
            name="Iron Pickaxe",
            item_type=ItemType.OTHER,
            rarity=Rarity.UNCOMMON,
            description="An iron pickaxe",
            max_stack_size=MaxStackSize(1)
        )

    @pytest.fixture
    def sample_recipes(self, sample_item_spec_wood, sample_item_spec_stone, sample_item_spec_iron, sample_item_spec_sword, sample_item_spec_pickaxe):
        """テスト用のレシピリストを作成"""
        wooden_sword_recipe = RecipeAggregate(
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

        iron_pickaxe_recipe = RecipeAggregate(
            recipe_id=RecipeId(2),
            name="Iron Pickaxe Recipe",
            description="Craft an iron pickaxe using iron and wood",
            ingredients=[
                RecipeIngredient(
                    item_spec_id=sample_item_spec_iron.item_spec_id,
                    quantity=3
                ),
                RecipeIngredient(
                    item_spec_id=sample_item_spec_wood.item_spec_id,
                    quantity=2
                )
            ],
            result=RecipeResult(
                item_spec_id=sample_item_spec_pickaxe.item_spec_id,
                quantity=1
            )
        )

        return [wooden_sword_recipe, iron_pickaxe_recipe]

    def test_find_recipes_by_result_item_existing_item(self, sample_recipes, sample_item_spec_sword):
        """存在する結果アイテムのレシピ検索テスト"""
        result = RecipeDomainService.find_recipes_by_result_item(
            sample_item_spec_sword.item_spec_id,
            sample_recipes
        )

        assert len(result) == 1
        assert result[0].recipe_id == RecipeId(1)
        assert result[0].name == "Wooden Sword Recipe"

    def test_find_recipes_by_result_item_non_existing_item(self, sample_recipes, sample_item_spec_iron):
        """存在しない結果アイテムのレシピ検索テスト"""
        result = RecipeDomainService.find_recipes_by_result_item(
            sample_item_spec_iron.item_spec_id,
            sample_recipes
        )

        assert len(result) == 0

    def test_find_recipes_by_result_item_empty_recipes(self, sample_item_spec_sword):
        """空のレシピリストでの検索テスト"""
        result = RecipeDomainService.find_recipes_by_result_item(
            sample_item_spec_sword.item_spec_id,
            []
        )

        assert len(result) == 0

    def test_find_recipes_by_ingredient_existing_ingredient(self, sample_recipes, sample_item_spec_wood):
        """存在する材料のレシピ検索テスト"""
        result = RecipeDomainService.find_recipes_by_ingredient(
            sample_item_spec_wood.item_spec_id,
            sample_recipes
        )

        assert len(result) == 2  # 両方のレシピで木材を使用
        recipe_ids = {recipe.recipe_id for recipe in result}
        assert recipe_ids == {RecipeId(1), RecipeId(2)}

    def test_find_recipes_by_ingredient_non_existing_ingredient(self, sample_recipes, sample_item_spec_stone):
        """存在しない材料のレシピ検索テスト（石は1つのレシピでのみ使用）"""
        result = RecipeDomainService.find_recipes_by_ingredient(
            sample_item_spec_stone.item_spec_id,
            sample_recipes
        )

        assert len(result) == 1
        assert result[0].recipe_id == RecipeId(1)

    def test_find_recipes_by_ingredient_unused_ingredient(self, sample_recipes, sample_item_spec_pickaxe):
        """どのレシピでも使用されていない材料の検索テスト"""
        result = RecipeDomainService.find_recipes_by_ingredient(
            sample_item_spec_pickaxe.item_spec_id,
            sample_recipes
        )

        assert len(result) == 0

    def test_find_recipes_by_ingredient_empty_recipes(self, sample_item_spec_wood):
        """空のレシピリストでの材料検索テスト"""
        result = RecipeDomainService.find_recipes_by_ingredient(
            sample_item_spec_wood.item_spec_id,
            []
        )

        assert len(result) == 0

    def test_can_player_craft_recipe_sufficient_inventory(self, sample_recipes, sample_item_spec_wood, sample_item_spec_stone):
        """十分なインベントリがある場合の合成可能チェックテスト"""
        recipe = sample_recipes[0]  # Wooden Sword Recipe

        # 十分なインベントリを作成
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=5  # 必要:2
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(2),
                item_spec=sample_item_spec_stone,
                quantity=3  # 必要:1
            )
        ]

        assert RecipeDomainService.can_player_craft_recipe(recipe, inventory)

    def test_can_player_craft_recipe_insufficient_inventory(self, sample_recipes, sample_item_spec_wood, sample_item_spec_stone):
        """不十分なインベントリがある場合の合成不可チェックテスト"""
        recipe = sample_recipes[0]  # Wooden Sword Recipe

        # 不十分なインベントリを作成（木材が不足）
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=1  # 必要:2, 不足
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(2),
                item_spec=sample_item_spec_stone,
                quantity=3  # 必要:1, 十分
            )
        ]

        assert not RecipeDomainService.can_player_craft_recipe(recipe, inventory)

    def test_can_player_craft_recipe_empty_inventory(self, sample_recipes):
        """空のインベントリでの合成不可チェックテスト"""
        recipe = sample_recipes[0]  # Wooden Sword Recipe

        assert not RecipeDomainService.can_player_craft_recipe(recipe, [])

    def test_can_player_craft_recipe_missing_ingredient_type(self, sample_recipes, sample_item_spec_wood):
        """必要な材料タイプが存在しない場合の合成不可チェックテスト"""
        recipe = sample_recipes[0]  # Wooden Sword Recipe

        # 石がないインベントリ
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=5  # 十分
            )
            # 石なし
        ]

        assert not RecipeDomainService.can_player_craft_recipe(recipe, inventory)

    def test_get_available_recipes_for_player_all_available(self, sample_recipes, sample_item_spec_wood, sample_item_spec_stone, sample_item_spec_iron):
        """全てのレシピが利用可能な場合のテスト"""
        # 全ての材料が十分にあるインベントリ
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=10  # Wooden Sword:2, Iron Pickaxe:2
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(2),
                item_spec=sample_item_spec_stone,
                quantity=5   # Wooden Sword:1
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(3),
                item_spec=sample_item_spec_iron,
                quantity=5   # Iron Pickaxe:3
            )
        ]

        available_recipes = RecipeDomainService.get_available_recipes_for_player(sample_recipes, inventory)

        assert len(available_recipes) == 2
        recipe_ids = {recipe.recipe_id for recipe in available_recipes}
        assert recipe_ids == {RecipeId(1), RecipeId(2)}

    def test_get_available_recipes_for_player_partial_available(self, sample_recipes, sample_item_spec_wood, sample_item_spec_stone, sample_item_spec_iron):
        """一部のレシピのみ利用可能な場合のテスト"""
        # Iron Pickaxeの材料（鉄）が不足
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=10  # 十分
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(2),
                item_spec=sample_item_spec_stone,
                quantity=5   # 十分
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(3),
                item_spec=sample_item_spec_iron,
                quantity=2   # Iron Pickaxe需要:3, 不足
            )
        ]

        available_recipes = RecipeDomainService.get_available_recipes_for_player(sample_recipes, inventory)

        assert len(available_recipes) == 1
        assert available_recipes[0].recipe_id == RecipeId(1)  # Wooden Swordのみ

    def test_get_available_recipes_for_player_none_available(self, sample_recipes, sample_item_spec_wood):
        """利用可能なレシピがない場合のテスト"""
        # 材料が全くないインベントリ
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=1  # 両レシピの需要を満たさない
            )
        ]

        available_recipes = RecipeDomainService.get_available_recipes_for_player(sample_recipes, inventory)

        assert len(available_recipes) == 0

    def test_get_available_recipes_for_player_empty_recipes(self, sample_item_spec_wood):
        """空のレシピリストでのテスト"""
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=10
            )
        ]

        available_recipes = RecipeDomainService.get_available_recipes_for_player([], inventory)

        assert len(available_recipes) == 0

    def test_get_available_recipes_for_player_empty_inventory(self, sample_recipes):
        """空のインベントリでのテスト"""
        available_recipes = RecipeDomainService.get_available_recipes_for_player(sample_recipes, [])

        assert len(available_recipes) == 0

    def test_calculate_inventory_quantities_single_item(self, sample_item_spec_wood):
        """単一アイテムのインベントリ数量計算テスト"""
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=5
            )
        ]

        quantities = RecipeAggregate.calculate_available_quantities(inventory)

        assert len(quantities) == 1
        assert quantities[sample_item_spec_wood.item_spec_id] == 5

    def test_calculate_inventory_quantities_multiple_different_items(self, sample_item_spec_wood, sample_item_spec_stone):
        """異なる複数アイテムのインベントリ数量計算テスト"""
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=5
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(2),
                item_spec=sample_item_spec_stone,
                quantity=3
            )
        ]

        quantities = RecipeAggregate.calculate_available_quantities(inventory)

        assert len(quantities) == 2
        assert quantities[sample_item_spec_wood.item_spec_id] == 5
        assert quantities[sample_item_spec_stone.item_spec_id] == 3

    def test_calculate_inventory_quantities_same_spec_multiple_items(self, sample_item_spec_wood):
        """同じスペックの複数アイテムのインベントリ数量計算テスト"""
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=5
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(2),
                item_spec=sample_item_spec_wood,
                quantity=3
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(3),
                item_spec=sample_item_spec_wood,
                quantity=2
            )
        ]

        quantities = RecipeAggregate.calculate_available_quantities(inventory)

        assert len(quantities) == 1
        assert quantities[sample_item_spec_wood.item_spec_id] == 10  # 5 + 3 + 2

    def test_calculate_inventory_quantities_empty_inventory(self):
        """空のインベントリの数量計算テスト"""
        quantities = RecipeAggregate.calculate_available_quantities([])

        assert len(quantities) == 0

    def test_calculate_inventory_quantities_mixed_specs(self, sample_item_spec_wood, sample_item_spec_stone):
        """混合スペックのインベントリ数量計算テスト"""
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=5
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(2),
                item_spec=sample_item_spec_stone,
                quantity=3
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(3),
                item_spec=sample_item_spec_wood,
                quantity=2
            ),
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(4),
                item_spec=sample_item_spec_stone,
                quantity=1
            )
        ]

        quantities = RecipeAggregate.calculate_available_quantities(inventory)

        assert len(quantities) == 2
        assert quantities[sample_item_spec_wood.item_spec_id] == 7   # 5 + 2
        assert quantities[sample_item_spec_stone.item_spec_id] == 4   # 3 + 1
