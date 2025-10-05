import pytest
from src.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from src.domain.item.value_object.recipe_id import RecipeId
from src.domain.item.value_object.recipe_ingredient import RecipeIngredient
from src.domain.item.value_object.recipe_result import RecipeResult
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.exception import InvalidRecipeException
from src.domain.item.aggregate.item_aggregate import ItemAggregate
from src.domain.item.value_object.item_spec import ItemSpec
from src.domain.item.value_object.max_stack_size import MaxStackSize
from src.domain.item.enum.item_enum import ItemType, Rarity


class TestRecipeAggregate:
    """RecipeAggregate集約のテスト"""

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
    def sample_item_spec_sword(self):
        """剣アイテム仕様を作成"""
        return ItemSpec(
            item_spec_id=ItemSpecId(3),
            name="Wooden Sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
            description="A wooden sword",
            max_stack_size=MaxStackSize(1)
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

    def test_create_valid_recipe_aggregate(self, sample_recipe):
        """正常なレシピ集約作成のテスト"""
        assert sample_recipe.recipe_id == RecipeId(1)
        assert sample_recipe.name == "Wooden Sword Recipe"
        assert sample_recipe.description == "Craft a wooden sword using wood and stone"
        assert len(sample_recipe.ingredients) == 2
        assert sample_recipe.result.item_spec_id == ItemSpecId(3)
        assert sample_recipe.result.quantity == 1

    def test_create_recipe_with_empty_name_raises_error(self, sample_item_spec_wood, sample_item_spec_sword):
        """空の名前での作成はエラーになるテスト"""
        with pytest.raises(InvalidRecipeException) as exc_info:
            RecipeAggregate(
                recipe_id=RecipeId(1),
                name="",  # 空の名前
                description="Test description",
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

        assert exc_info.value.recipe_id == 1
        assert "name must not be empty" in exc_info.value.reason

    def test_create_recipe_with_whitespace_name_raises_error(self, sample_item_spec_wood, sample_item_spec_sword):
        """空白のみの名前での作成はエラーになるテスト"""
        with pytest.raises(InvalidRecipeException) as exc_info:
            RecipeAggregate(
                recipe_id=RecipeId(1),
                name="   ",  # 空白のみ
                description="Test description",
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

        assert exc_info.value.recipe_id == 1
        assert "name must not be empty" in exc_info.value.reason

    def test_create_recipe_with_empty_description_raises_error(self, sample_item_spec_wood, sample_item_spec_sword):
        """空の説明での作成はエラーになるテスト"""
        with pytest.raises(InvalidRecipeException) as exc_info:
            RecipeAggregate(
                recipe_id=RecipeId(1),
                name="Test Recipe",
                description="",  # 空の説明
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

        assert exc_info.value.recipe_id == 1
        assert "description must not be empty" in exc_info.value.reason

    def test_create_recipe_with_empty_ingredients_raises_error(self, sample_item_spec_sword):
        """空の材料リストでの作成はエラーになるテスト"""
        with pytest.raises(InvalidRecipeException) as exc_info:
            RecipeAggregate(
                recipe_id=RecipeId(1),
                name="Test Recipe",
                description="Test description",
                ingredients=[],  # 空の材料リスト
                result=RecipeResult(
                    item_spec_id=sample_item_spec_sword.item_spec_id,
                    quantity=1
                )
            )

        assert exc_info.value.recipe_id == 1
        assert "ingredients must not be empty" in exc_info.value.reason

    def test_create_recipe_with_duplicate_ingredients_raises_error(self, sample_item_spec_wood, sample_item_spec_sword):
        """重複した材料での作成はエラーになるテスト"""
        with pytest.raises(InvalidRecipeException) as exc_info:
            RecipeAggregate(
                recipe_id=RecipeId(1),
                name="Test Recipe",
                description="Test description",
                ingredients=[
                    RecipeIngredient(
                        item_spec_id=sample_item_spec_wood.item_spec_id,
                        quantity=1
                    ),
                    RecipeIngredient(
                        item_spec_id=sample_item_spec_wood.item_spec_id,  # 重複
                        quantity=2
                    )
                ],
                result=RecipeResult(
                    item_spec_id=sample_item_spec_sword.item_spec_id,
                    quantity=1
                )
            )

        assert exc_info.value.recipe_id == 1
        assert "ingredients must have unique item_spec_ids" in exc_info.value.reason

    def test_can_craft_with_sufficient_ingredients(self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone):
        """十分な材料がある場合の合成可能チェック"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 5,  # 必要:2, 十分
            sample_item_spec_stone.item_spec_id: 3   # 必要:1, 十分
        }

        assert sample_recipe.can_craft_with(available_items)

    def test_can_craft_with_exact_ingredients(self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone):
        """必要な分ちょうどの材料がある場合の合成可能チェック"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 2,  # 必要:2, ちょうど
            sample_item_spec_stone.item_spec_id: 1   # 必要:1, ちょうど
        }

        assert sample_recipe.can_craft_with(available_items)

    def test_can_craft_with_insufficient_wood(self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone):
        """木材が不足している場合の合成不可チェック"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 1,  # 必要:2, 不足
            sample_item_spec_stone.item_spec_id: 3   # 必要:1, 十分
        }

        assert not sample_recipe.can_craft_with(available_items)

    def test_can_craft_with_insufficient_stone(self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone):
        """石が不足している場合の合成不可チェック"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 5,  # 必要:2, 十分
            sample_item_spec_stone.item_spec_id: 0   # 必要:1, 不足
        }

        assert not sample_recipe.can_craft_with(available_items)

    def test_can_craft_with_missing_ingredient_spec(self, sample_recipe, sample_item_spec_wood):
        """必要な材料スペックが存在しない場合の合成不可チェック"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 5,  # 木材はある
            # 石がない
        }

        assert not sample_recipe.can_craft_with(available_items)

    def test_can_craft_with_empty_available_items(self, sample_recipe):
        """利用可能なアイテムが空の場合の合成不可チェック"""
        assert not sample_recipe.can_craft_with({})

    def test_can_craft_with_extra_ingredients(self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone, sample_item_spec_sword):
        """余分な材料がある場合でも必要な材料があれば合成可能"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 5,    # 必要:2, 十分
            sample_item_spec_stone.item_spec_id: 3,   # 必要:1, 十分
            sample_item_spec_sword.item_spec_id: 10   # 余分な材料
        }

        assert sample_recipe.can_craft_with(available_items)

    def test_get_missing_ingredients_none_missing(self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone):
        """全ての材料が十分にある場合の不足材料取得"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 5,  # 必要:2, 十分
            sample_item_spec_stone.item_spec_id: 3   # 必要:1, 十分
        }

        missing = sample_recipe.get_missing_ingredients(available_items)
        assert len(missing) == 0

    def test_get_missing_ingredients_partial_missing(self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone):
        """一部材料が不足している場合の不足材料取得"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 1,  # 必要:2, 不足1個
            sample_item_spec_stone.item_spec_id: 3   # 必要:1, 十分
        }

        missing = sample_recipe.get_missing_ingredients(available_items)
        assert len(missing) == 1

        missing_wood = next(m for m in missing if m.item_spec_id == sample_item_spec_wood.item_spec_id)
        assert missing_wood.quantity == 1  # 不足数量

    def test_get_missing_ingredients_all_missing(self, sample_recipe, sample_item_spec_wood, sample_item_spec_stone):
        """全ての材料が不足している場合の不足材料取得"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 0,  # 必要:2, 不足2個
            sample_item_spec_stone.item_spec_id: 0   # 必要:1, 不足1個
        }

        missing = sample_recipe.get_missing_ingredients(available_items)
        assert len(missing) == 2

        missing_wood = next(m for m in missing if m.item_spec_id == sample_item_spec_wood.item_spec_id)
        assert missing_wood.quantity == 2

        missing_stone = next(m for m in missing if m.item_spec_id == sample_item_spec_stone.item_spec_id)
        assert missing_stone.quantity == 1

    def test_get_missing_ingredients_missing_spec(self, sample_recipe, sample_item_spec_wood):
        """必要な材料スペックが存在しない場合の不足材料取得"""
        available_items = {
            sample_item_spec_wood.item_spec_id: 5,  # 木材はある
            # 石がない
        }

        missing = sample_recipe.get_missing_ingredients(available_items)
        assert len(missing) == 1

        missing_stone = next(m for m in missing if m.item_spec_id == ItemSpecId(2))
        assert missing_stone.quantity == 1

    def test_calculate_available_quantities_empty_inventory(self):
        """空のインベントリからの数量計算"""
        available = RecipeAggregate.calculate_available_quantities([])
        assert len(available) == 0

    def test_calculate_available_quantities_single_item(self, sample_item_spec_wood):
        """単一アイテムのインベントリからの数量計算"""
        inventory = [
            ItemAggregate.create(
                item_instance_id=ItemInstanceId(1),
                item_spec=sample_item_spec_wood,
                quantity=5
            )
        ]

        available = RecipeAggregate.calculate_available_quantities(inventory)
        assert len(available) == 1
        assert available[sample_item_spec_wood.item_spec_id] == 5

    def test_calculate_available_quantities_multiple_different_items(self, sample_item_spec_wood, sample_item_spec_stone):
        """異なる複数アイテムのインベントリからの数量計算"""
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

        available = RecipeAggregate.calculate_available_quantities(inventory)
        assert len(available) == 2
        assert available[sample_item_spec_wood.item_spec_id] == 5
        assert available[sample_item_spec_stone.item_spec_id] == 3

    def test_calculate_available_quantities_same_spec_multiple_items(self, sample_item_spec_wood):
        """同じスペックの複数アイテムのインベントリからの数量計算"""
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

        available = RecipeAggregate.calculate_available_quantities(inventory)
        assert len(available) == 1
        assert available[sample_item_spec_wood.item_spec_id] == 10  # 5 + 3 + 2

    def test_equality_same_recipe(self, sample_recipe):
        """同じレシピの等価性テスト"""
        recipe2 = RecipeAggregate(
            recipe_id=RecipeId(1),  # 同じID
            name="Different Name",  # 異なる名前（等価性に関係なし）
            description="Different Description",
            ingredients=[
                RecipeIngredient(
                    item_spec_id=ItemSpecId(1),
                    quantity=2
                ),
                RecipeIngredient(
                    item_spec_id=ItemSpecId(2),
                    quantity=1
                )
            ],
            result=RecipeResult(
                item_spec_id=ItemSpecId(3),
                quantity=1
            )
        )

        assert sample_recipe == recipe2
        assert hash(sample_recipe) == hash(recipe2)

    def test_equality_different_recipe(self, sample_recipe):
        """異なるレシピの非等価性テスト"""
        recipe2 = RecipeAggregate(
            recipe_id=RecipeId(2),  # 異なるID
            name="Wooden Sword Recipe",
            description="Craft a wooden sword using wood and stone",
            ingredients=[
                RecipeIngredient(
                    item_spec_id=ItemSpecId(1),
                    quantity=2
                ),
                RecipeIngredient(
                    item_spec_id=ItemSpecId(2),
                    quantity=1
                )
            ],
            result=RecipeResult(
                item_spec_id=ItemSpecId(3),
                quantity=1
            )
        )

        assert sample_recipe != recipe2
        assert hash(sample_recipe) != hash(recipe2)

    def test_equality_with_non_recipe_aggregate(self, sample_recipe):
        """RecipeAggregate以外との比較テスト"""
        assert sample_recipe != "not a recipe"
        assert sample_recipe != 42
        assert sample_recipe != None

    def test_string_representation(self, sample_recipe):
        """文字列表現のテスト"""
        str_repr = str(sample_recipe)
        assert "RecipeAggregate" in str_repr
        assert "Wooden Sword Recipe" in str_repr
        assert "1 x2" in str_repr  # 木材: ID=1, 数量=2
        assert "2 x1" in str_repr  # 石: ID=2, 数量=1
        assert "3 x1" in str_repr  # 剣: ID=3, 数量=1

    def test_properties_access(self, sample_recipe):
        """プロパティアクセスのテスト"""
        assert sample_recipe.recipe_id == RecipeId(1)
        assert sample_recipe.name == "Wooden Sword Recipe"
        assert sample_recipe.description == "Craft a wooden sword using wood and stone"

        ingredients = sample_recipe.ingredients
        assert len(ingredients) == 2
        assert ingredients[0].item_spec_id == ItemSpecId(1)
        assert ingredients[0].quantity == 2
        assert ingredients[1].item_spec_id == ItemSpecId(2)
        assert ingredients[1].quantity == 1

        # ingredientsはコピーを返すことを確認
        ingredients_copy = sample_recipe.ingredients
        ingredients_copy.clear()
        assert len(sample_recipe.ingredients) == 2  # 元のリストは変更されていない

        assert sample_recipe.result.item_spec_id == ItemSpecId(3)
        assert sample_recipe.result.quantity == 1

    def test_single_ingredient_recipe(self, sample_item_spec_wood, sample_item_spec_sword):
        """単一材料のレシピテスト"""
        recipe = RecipeAggregate(
            recipe_id=RecipeId(2),
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

        # 合成可能チェック
        available_items = {sample_item_spec_wood.item_spec_id: 1}
        assert recipe.can_craft_with(available_items)

        # 不足材料チェック
        available_items_insufficient = {sample_item_spec_wood.item_spec_id: 0}
        assert not recipe.can_craft_with(available_items_insufficient)

        missing = recipe.get_missing_ingredients(available_items_insufficient)
        assert len(missing) == 1
        assert missing[0].quantity == 1

    def test_large_quantity_recipe(self, sample_item_spec_wood, sample_item_spec_stone, sample_item_spec_sword):
        """大量材料が必要なレシピテスト"""
        recipe = RecipeAggregate(
            recipe_id=RecipeId(3),
            name="Massive Recipe",
            description="Requires many materials",
            ingredients=[
                RecipeIngredient(
                    item_spec_id=sample_item_spec_wood.item_spec_id,
                    quantity=10
                ),
                RecipeIngredient(
                    item_spec_id=sample_item_spec_stone.item_spec_id,
                    quantity=5
                )
            ],
            result=RecipeResult(
                item_spec_id=sample_item_spec_sword.item_spec_id,
                quantity=1
            )
        )

        # 十分な材料
        available_sufficient = {
            sample_item_spec_wood.item_spec_id: 10,
            sample_item_spec_stone.item_spec_id: 5
        }
        assert recipe.can_craft_with(available_sufficient)

        # 木材不足
        available_insufficient_wood = {
            sample_item_spec_wood.item_spec_id: 9,   # 必要:10, 不足
            sample_item_spec_stone.item_spec_id: 5
        }
        assert not recipe.can_craft_with(available_insufficient_wood)

        missing = recipe.get_missing_ingredients(available_insufficient_wood)
        assert len(missing) == 1
        assert missing[0].item_spec_id == sample_item_spec_wood.item_spec_id
        assert missing[0].quantity == 1
