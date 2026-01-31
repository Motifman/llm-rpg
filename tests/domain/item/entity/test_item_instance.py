import pytest
from src.domain.item.entity.item_instance import ItemInstance
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_spec import ItemSpec
from src.domain.item.value_object.max_stack_size import MaxStackSize
from src.domain.item.value_object.durability import Durability
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from src.domain.item.exception import (
    QuantityValidationException,
    DurabilityValidationException,
    StackSizeExceededException,
    InsufficientQuantityException,
)


class TestItemInstance:
    """ItemInstanceエンティティのテスト"""

    @pytest.fixture
    def sample_item_spec(self):
        """テスト用のItemSpecを作成"""
        template_id = ItemSpecId(1)
        max_stack = MaxStackSize(64)
        return ItemSpec(
            item_spec_id=template_id,
            name="Test Sword",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="A test sword for testing",
            max_stack_size=max_stack,
            equipment_type=EquipmentType.WEAPON
        )

    @pytest.fixture
    def sample_item_instance(self, sample_item_spec):
        """テスト用のItemInstanceを作成"""
        item_id = ItemInstanceId(1)
        return ItemInstance(
            item_instance_id=item_id,
            item_spec=sample_item_spec
        )

    @pytest.fixture
    def item_instance_with_durability(self):
        """耐久度付きのItemInstanceを作成"""
        item_id = ItemInstanceId(2)
        template_id = ItemSpecId(2)
        max_stack = MaxStackSize(1)
        item_spec = ItemSpec(
            item_spec_id=template_id,
            name="Durable Sword",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.RARE,
            description="A durable sword for testing",
            max_stack_size=max_stack,
            durability_max=100,
            equipment_type=EquipmentType.WEAPON
        )
        durability = Durability(max_value=100, current=50)
        return ItemInstance(
            item_instance_id=item_id,
            item_spec=item_spec,
            durability=durability
        )

    def test_create_basic_item_instance(self, sample_item_instance):
        """基本的なItemInstance作成のテスト"""
        assert sample_item_instance.item_instance_id.value == 1
        assert sample_item_instance.name == "Test Sword"
        assert sample_item_instance.item_type == ItemType.EQUIPMENT
        assert sample_item_instance.max_stack_size.value == 64
        assert sample_item_instance.quantity == 1
        assert sample_item_instance.durability is None
        assert sample_item_instance.description == "A test sword for testing"

    def test_create_with_durability(self, item_instance_with_durability):
        """耐久度付きItemInstance作成のテスト"""
        assert item_instance_with_durability.durability is not None
        assert item_instance_with_durability.durability.max_value == 100
        assert item_instance_with_durability.durability.current == 50


    def test_use_basic_item(self, sample_item_instance):
        """基本アイテムの使用テスト"""
        success = sample_item_instance.use()
        assert success is True
        assert sample_item_instance.quantity == 1  # スタック不可なので減らない

    def test_use_item_with_durability(self, item_instance_with_durability):
        """耐久度付きアイテムの使用テスト"""
        success = item_instance_with_durability.use()
        assert success is True
        assert item_instance_with_durability.durability.current == 49  # 耐久度が減っている

    def test_use_broken_item(self):
        """破損したアイテムの使用テスト"""
        item_id = ItemInstanceId(6)
        template_id = ItemSpecId(6)
        max_stack = MaxStackSize(1)
        spec = ItemSpec(
            item_spec_id=template_id,
            name="Broken Sword",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="A broken sword",
            max_stack_size=max_stack,
            durability_max=100,
            equipment_type=EquipmentType.WEAPON
        )
        durability = Durability(max_value=100, current=0)  # 破損済み
        item = ItemInstance(
            item_instance_id=item_id,
            item_spec=spec,
            durability=durability
        )
        success = item.use()
        assert success is False
        assert item.durability.current == 0

    def test_can_stack_with_same_item(self, sample_item_spec):
        """同じスペックのアイテムとのスタックテスト"""
        item1 = ItemInstance(
            item_instance_id=ItemInstanceId(10),
            item_spec=sample_item_spec
        )
        item2 = ItemInstance(
            item_instance_id=ItemInstanceId(11),
            item_spec=sample_item_spec
        )
        assert item1.can_stack_with(item2)

    def test_cannot_stack_different_name(self, sample_item_spec):
        """異なるスペックのアイテムとのスタックテスト"""
        item1 = ItemInstance(
            item_instance_id=ItemInstanceId(10),
            item_spec=sample_item_spec
        )
        # 異なるスペックを作成
        different_spec = ItemSpec(
            item_spec_id=ItemSpecId(999),
            name="Different Sword",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="A different sword",
            max_stack_size=MaxStackSize(64),
            equipment_type=EquipmentType.WEAPON
        )
        item2 = ItemInstance(
            item_instance_id=ItemInstanceId(11),
            item_spec=different_spec
        )
        assert not item1.can_stack_with(item2)

    def test_cannot_stack_different_type(self, sample_item_spec):
        """異なるタイプのスペックのアイテムとのスタックテスト"""
        item1 = ItemInstance(
            item_instance_id=ItemInstanceId(10),
            item_spec=sample_item_spec
        )
        # 異なるタイプのスペックを作成
        different_type_spec = ItemSpec(
            item_spec_id=ItemSpecId(888),
            name="Test Sword",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="A test sword as consumable",
            max_stack_size=MaxStackSize(64)
        )
        item2 = ItemInstance(
            item_instance_id=ItemInstanceId(12),
            item_spec=different_type_spec
        )
        assert not item1.can_stack_with(item2)

    def test_cannot_stack_at_max_quantity(self):
        """最大数量時のスタックテスト"""
        limited_spec = ItemSpec(
            item_spec_id=ItemSpecId(777),
            name="Limited Item",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="An item with limited stack size",
            max_stack_size=MaxStackSize(2)
        )
        item = ItemInstance(
            item_instance_id=ItemInstanceId(13),
            item_spec=limited_spec
        )
        item.add_quantity(1)  # 最大まで追加

        other = ItemInstance(
            item_instance_id=ItemInstanceId(14),
            item_spec=limited_spec
        )
        assert not item.can_stack_with(other)

    def test_cannot_stack_durable_items(self):
        """耐久度付きアイテムはスタックできないテスト"""
        durable_spec = ItemSpec(
            item_spec_id=ItemSpecId(888),
            name="Durable Sword",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.RARE,
            description="A sword with durability",
            max_stack_size=MaxStackSize(1),  # 耐久度付きアイテムはmax_stack_size=1でなければならない
            durability_max=100,
            equipment_type=EquipmentType.WEAPON
        )

        item1 = ItemInstance(
            item_instance_id=ItemInstanceId(15),
            item_spec=durable_spec,
            durability=Durability(max_value=100, current=100)
        )

        item2 = ItemInstance(
            item_instance_id=ItemInstanceId(16),
            item_spec=durable_spec,
            durability=Durability(max_value=100, current=80)
        )

        # 同じスペックでも耐久度があるためスタックできない
        assert not item1.can_stack_with(item2)
        assert not item2.can_stack_with(item1)

    def test_add_quantity_success(self, sample_item_instance):
        """数量追加成功のテスト"""
        sample_item_instance.add_quantity(5)
        assert sample_item_instance.quantity == 6

    def test_invalid_quantity_negative(self):
        """無効な数量（負の値）のテスト"""
        template_id = ItemSpecId(100)
        max_stack = MaxStackSize(10)
        spec = ItemSpec(
            item_spec_id=template_id,
            name="Test Item",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="A test item",
            max_stack_size=max_stack,
            equipment_type=EquipmentType.WEAPON
        )
        item_id = ItemInstanceId(100)
        with pytest.raises(QuantityValidationException):
            ItemInstance(
                item_instance_id=item_id,
                item_spec=spec,
                quantity=-1
            )

    def test_invalid_durability_without_spec_max(self):
        """スペックに耐久度最大値がないのに耐久度を設定した場合のテスト"""
        template_id = ItemSpecId(101)
        max_stack = MaxStackSize(1)
        spec = ItemSpec(
            item_spec_id=template_id,
            name="Non-durable Item",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="An item without durability",
            max_stack_size=max_stack,
            equipment_type=EquipmentType.WEAPON
            # durability_maxは設定しない
        )
        item_id = ItemInstanceId(101)
        durability = Durability(max_value=100, current=100)
        with pytest.raises(DurabilityValidationException):
            ItemInstance(
                item_instance_id=item_id,
                item_spec=spec,
                durability=durability
            )

    def test_invalid_durability_max_mismatch(self):
        """耐久度の最大値がスペックのdurability_maxと一致しない場合のテスト"""
        template_id = ItemSpecId(102)
        max_stack = MaxStackSize(1)
        spec = ItemSpec(
            item_spec_id=template_id,
            name="Durable Item",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.UNCOMMON,
            description="An item with durability",
            max_stack_size=max_stack,
            durability_max=100,
            equipment_type=EquipmentType.WEAPON
        )
        item_id = ItemInstanceId(102)
        durability = Durability(max_value=200, current=200)  # スペックと一致しない
        with pytest.raises(DurabilityValidationException):
            ItemInstance(
                item_instance_id=item_id,
                item_spec=spec,
                durability=durability
            )

    def test_add_quantity_zero(self, sample_item_instance):
        """0数量追加のテスト"""
        with pytest.raises(QuantityValidationException):
            sample_item_instance.add_quantity(0)

    def test_add_quantity_negative(self, sample_item_instance):
        """負の数量追加のテスト"""
        with pytest.raises(QuantityValidationException):
            sample_item_instance.add_quantity(-1)

    def test_add_quantity_over_max(self, sample_item_instance):
        """最大数量超過のテスト"""
        with pytest.raises(StackSizeExceededException):
            sample_item_instance.add_quantity(64)  # 既に1あるので65になる

    def test_remove_quantity_success(self, sample_item_instance):
        """数量削除成功のテスト"""
        sample_item_instance.add_quantity(5)
        sample_item_instance.remove_quantity(3)
        assert sample_item_instance.quantity == 3

    def test_remove_quantity_zero(self, sample_item_instance):
        """0数量削除のテスト"""
        with pytest.raises(QuantityValidationException):
            sample_item_instance.remove_quantity(0)

    def test_remove_quantity_insufficient(self, sample_item_instance):
        """数量不足のテスト"""
        with pytest.raises(InsufficientQuantityException):
            sample_item_instance.remove_quantity(2)

    def test_equality(self, sample_item_instance, sample_item_spec):
        """等価性テスト"""
        same_id = ItemInstance(
            item_instance_id=ItemInstanceId(1),
            item_spec=sample_item_spec  # 同じスペックでもIDが同じなら等価
        )
        different_id = ItemInstance(
            item_instance_id=ItemInstanceId(2),
            item_spec=sample_item_spec  # IDが異なるので非等価
        )

        assert sample_item_instance == same_id
        assert sample_item_instance != different_id

    def test_hash(self, sample_item_instance, sample_item_spec):
        """ハッシュテスト"""
        same_id = ItemInstance(
            item_instance_id=ItemInstanceId(1),
            item_spec=sample_item_spec
        )

        assert hash(sample_item_instance) == hash(same_id)

        # setで重複を除去できる
        items = {sample_item_instance, same_id}
        assert len(items) == 1

    def test_repr(self, sample_item_instance):
        """文字列表現のテスト"""
        repr_str = repr(sample_item_instance)
        assert "ItemInstance" in repr_str
        assert "id=1" in repr_str
        assert "name=Test Sword" in repr_str
        assert "qty=1" in repr_str

    def test_invalid_quantity_over_max_stack_size(self):
        """quantityがmax_stack_sizeを超える場合のテスト"""
        template_id = ItemSpecId(103)
        max_stack = MaxStackSize(10)
        spec = ItemSpec(
            item_spec_id=template_id,
            name="Limited Item",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="An item with limited stack size",
            max_stack_size=max_stack
        )
        item_id = ItemInstanceId(103)

        with pytest.raises(StackSizeExceededException) as exc_info:
            ItemInstance(
                item_instance_id=item_id,
                item_spec=spec,
                quantity=15  # max_stack_size(10)を超える
            )

        # エラーメッセージに適切な情報が含まれていることを確認
        assert "Stack size exceeded: current 15, max 10" in str(exc_info.value)

    def test_durability_item_must_have_max_stack_size_one(self):
        """耐久度付きアイテムはmax_stack_sizeが1であることをテスト"""
        # 正常な耐久度付きアイテムの作成テスト
        valid_spec = ItemSpec(
            item_spec_id=ItemSpecId(104),
            name="Valid Durable Item",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="An item with durability and correct stack size",
            max_stack_size=MaxStackSize(1),  # 正しい
            durability_max=100,
            equipment_type=EquipmentType.WEAPON
        )

        # このspecでは正常に作成できるはず
        instance = ItemInstance(
            item_instance_id=ItemInstanceId(104),
            item_spec=valid_spec,
            durability=Durability(max_value=100, current=100)
        )
        assert instance.durability is not None
        assert instance.max_stack_size.value == 1

        # ItemSpecレベルでmax_stack_size != 1の耐久度付きアイテムは作成できないので、
        # ここでは正常系のテストのみ実施
