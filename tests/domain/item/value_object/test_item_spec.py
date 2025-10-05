import pytest
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_spec import ItemSpec
from src.domain.item.value_object.max_stack_size import MaxStackSize
from src.domain.item.enum.item_enum import ItemType, Rarity
from src.domain.item.exception import ItemSpecValidationException


class TestItemSpec:
    """ItemSpec値オブジェクトのテスト"""

    @pytest.fixture
    def sample_item_spec(self):
        """テスト用のItemSpecを作成"""
        template_id = ItemSpecId(1)
        max_stack = MaxStackSize(64)
        return ItemSpec(
            item_spec_id=template_id,
            name="Test Sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
            description="A test sword for testing",
            max_stack_size=max_stack
        )

    def test_create_basic_item_spec(self, sample_item_spec):
        """基本的なItemSpec作成のテスト"""
        assert sample_item_spec.item_spec_id.value == 1
        assert sample_item_spec.name == "Test Sword"
        assert sample_item_spec.item_type == ItemType.WEAPON
        assert sample_item_spec.description == "A test sword for testing"
        assert sample_item_spec.max_stack_size.value == 64
        assert sample_item_spec.durability_max is None
        assert not sample_item_spec.can_create_durability()

    def test_create_with_durability_max(self):
        """耐久度最大値付きItemSpec作成のテスト"""
        template_id = ItemSpecId(2)
        max_stack = MaxStackSize(1)
        spec = ItemSpec(
            item_spec_id=template_id,
            name="Durable Sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.UNCOMMON,
            description="A durable sword",
            max_stack_size=max_stack,
            durability_max=100
        )
        assert spec.durability_max == 100
        assert spec.can_create_durability()

    def test_invalid_name_empty(self):
        """無効な名前（空文字）のテスト"""
        template_id = ItemSpecId(3)
        max_stack = MaxStackSize(10)
        with pytest.raises(ItemSpecValidationException):
            ItemSpec(
                item_spec_id=template_id,
                name="",
                item_type=ItemType.WEAPON,
                rarity=Rarity.COMMON,
                description="A sword",
                max_stack_size=max_stack
            )

    def test_invalid_name_whitespace(self):
        """無効な名前（空白のみ）のテスト"""
        template_id = ItemSpecId(4)
        max_stack = MaxStackSize(10)
        with pytest.raises(ItemSpecValidationException):
            ItemSpec(
                item_spec_id=template_id,
                name="   ",
                item_type=ItemType.WEAPON,
                rarity=Rarity.COMMON,
                description="A sword",
                max_stack_size=max_stack
            )

    def test_invalid_description_empty(self):
        """無効な説明（空文字）のテスト"""
        template_id = ItemSpecId(5)
        max_stack = MaxStackSize(10)
        with pytest.raises(ItemSpecValidationException):
            ItemSpec(
                item_spec_id=template_id,
                name="Sword",
                item_type=ItemType.WEAPON,
                rarity=Rarity.COMMON,
                description="",
                max_stack_size=max_stack
            )

    def test_invalid_durability_max_zero(self):
        """無効な耐久度最大値（0）のテスト"""
        template_id = ItemSpecId(6)
        max_stack = MaxStackSize(10)
        with pytest.raises(ItemSpecValidationException):
            ItemSpec(
                item_spec_id=template_id,
                name="Sword",
                item_type=ItemType.WEAPON,
                rarity=Rarity.COMMON,
                description="A sword",
                max_stack_size=max_stack,
                durability_max=0
            )

    def test_invalid_durability_max_negative(self):
        """無効な耐久度最大値（負の値）のテスト"""
        template_id = ItemSpecId(7)
        max_stack = MaxStackSize(10)
        with pytest.raises(ItemSpecValidationException):
            ItemSpec(
                item_spec_id=template_id,
                name="Sword",
                item_type=ItemType.WEAPON,
                rarity=Rarity.COMMON,
                description="A sword",
                max_stack_size=max_stack,
                durability_max=-1
            )

    def test_equality_same_spec(self, sample_item_spec):
        """同じスペックの等価性テスト"""
        same_spec = ItemSpec(
            item_spec_id=ItemSpecId(1),  # 同じID
            name="Different Name",  # 異なる名前だがIDが同じなので等価
            item_type=ItemType.CONSUMABLE,  # 異なるタイプ
            rarity=Rarity.RARE,  # 異なるレアリティ
            description="Different description",  # 異なる説明
            max_stack_size=MaxStackSize(32)  # 異なるスタックサイズ
        )
        assert sample_item_spec == same_spec

    def test_equality_different_spec(self, sample_item_spec):
        """異なるスペックの等価性テスト"""
        different_spec = ItemSpec(
            item_spec_id=ItemSpecId(999),  # 異なるID
            name="Test Sword",
            item_type=ItemType.WEAPON,
            rarity=Rarity.COMMON,
            description="A test sword for testing",
            max_stack_size=MaxStackSize(64)
        )
        assert sample_item_spec != different_spec

    def test_hash(self, sample_item_spec):
        """ハッシュテスト"""
        same_spec = ItemSpec(
            item_spec_id=ItemSpecId(1),
            name="Different Name",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.RARE,
            description="Different description",
            max_stack_size=MaxStackSize(32)
        )

        assert hash(sample_item_spec) == hash(same_spec)

        # setで重複を除去できる
        specs = {sample_item_spec, same_spec}
        assert len(specs) == 1

    def test_immutable(self, sample_item_spec):
        """不変性のテスト"""
        with pytest.raises(AttributeError):
            sample_item_spec.name = "New Name"
