import pytest
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from ai_rpg_world.domain.item.exception import ItemSpecValidationException


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
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="A test sword for testing",
            max_stack_size=max_stack,
            equipment_type=EquipmentType.WEAPON
        )

    def test_create_basic_item_spec(self, sample_item_spec):
        """基本的なItemSpec作成のテスト"""
        assert sample_item_spec.item_spec_id.value == 1
        assert sample_item_spec.name == "Test Sword"
        assert sample_item_spec.item_type == ItemType.EQUIPMENT
        assert sample_item_spec.equipment_type == EquipmentType.WEAPON
        assert sample_item_spec.description == "A test sword for testing"
        assert sample_item_spec.max_stack_size.value == 64
        assert sample_item_spec.durability_max is None
        assert not sample_item_spec.can_create_durability()
        assert sample_item_spec.is_equipment()
        assert sample_item_spec.get_equipment_type() == EquipmentType.WEAPON

    def test_create_with_durability_max_valid_stack_size(self):
        """耐久度最大値付きItemSpec作成のテスト（有効なスタックサイズ）"""
        template_id = ItemSpecId(2)
        max_stack = MaxStackSize(1)  # 耐久度付きアイテムはスタックサイズ1でなければならない
        spec = ItemSpec(
            item_spec_id=template_id,
            name="Durable Sword",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.UNCOMMON,
            description="A durable sword",
            max_stack_size=max_stack,
            durability_max=100,
            equipment_type=EquipmentType.WEAPON
        )
        assert spec.durability_max == 100
        assert spec.can_create_durability()
        assert spec.max_stack_size.value == 1
        assert spec.equipment_type == EquipmentType.WEAPON

    def test_invalid_name_empty(self):
        """無効な名前（空文字）のテスト"""
        template_id = ItemSpecId(3)
        max_stack = MaxStackSize(10)
        with pytest.raises(ItemSpecValidationException):
            ItemSpec(
                item_spec_id=template_id,
                name="",
                item_type=ItemType.EQUIPMENT,
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
                item_type=ItemType.EQUIPMENT,
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
                item_type=ItemType.EQUIPMENT,
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
                item_type=ItemType.EQUIPMENT,
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
                item_type=ItemType.EQUIPMENT,
                rarity=Rarity.COMMON,
                description="A sword",
                max_stack_size=max_stack,
                durability_max=-1
            )

    def test_invalid_max_stack_size_with_durability(self):
        """耐久度付きアイテムで無効な最大スタックサイズのテスト"""
        template_id = ItemSpecId(8)
        max_stack = MaxStackSize(10)  # 耐久度付きアイテムはスタックサイズ1でなければならない
        with pytest.raises(ItemSpecValidationException) as exc_info:
            ItemSpec(
                item_spec_id=template_id,
                name="Durable Sword",
                item_type=ItemType.EQUIPMENT,
                rarity=Rarity.UNCOMMON,
                description="A durable sword",
                max_stack_size=max_stack,
                durability_max=100
            )

        # エラーメッセージに適切な理由が含まれていることを確認
        assert "items with durability must have max_stack_size of 1" in str(exc_info.value)

    def test_invalid_equipment_without_equipment_type(self):
        """装備品なのにequipment_typeが指定されていない場合のテスト"""
        template_id = ItemSpecId(9)
        max_stack = MaxStackSize(1)
        with pytest.raises(ItemSpecValidationException) as exc_info:
            ItemSpec(
                item_spec_id=template_id,
                name="Sword without equipment type",
                item_type=ItemType.EQUIPMENT,
                rarity=Rarity.COMMON,
                description="A sword",
                max_stack_size=max_stack
                # equipment_type=None (デフォルト値)
            )

        assert "equipment items must have equipment_type" in str(exc_info.value)

    def test_invalid_non_equipment_with_equipment_type(self):
        """非装備品なのにequipment_typeが指定されている場合のテスト"""
        template_id = ItemSpecId(10)
        max_stack = MaxStackSize(64)
        with pytest.raises(ItemSpecValidationException) as exc_info:
            ItemSpec(
                item_spec_id=template_id,
                name="Potion with equipment type",
                item_type=ItemType.CONSUMABLE,
                rarity=Rarity.COMMON,
                description="A potion",
                max_stack_size=max_stack,
                equipment_type=EquipmentType.WEAPON  # 誤って指定
            )

        assert "non-equipment items must not have equipment_type" in str(exc_info.value)

    def test_create_consumable_item(self):
        """消費アイテム作成のテスト（equipment_typeはNone）"""
        template_id = ItemSpecId(11)
        max_stack = MaxStackSize(64)
        spec = ItemSpec(
            item_spec_id=template_id,
            name="Health Potion",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="Restores health",
            max_stack_size=max_stack
            # equipment_type=None (デフォルト値)
        )
        assert spec.item_type == ItemType.CONSUMABLE
        assert spec.equipment_type is None
        assert not spec.is_equipment()
        assert spec.get_equipment_type() is None

    def test_create_equipment_items_different_types(self):
        """異なる装備タイプのアイテム作成テスト"""
        # ヘルメット
        helmet_spec = ItemSpec(
            item_spec_id=ItemSpecId(12),
            name="Iron Helmet",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="Protects the head",
            max_stack_size=MaxStackSize(1),
            equipment_type=EquipmentType.HELMET
        )
        assert helmet_spec.equipment_type == EquipmentType.HELMET
        assert helmet_spec.is_equipment()

        # 鎧
        armor_spec = ItemSpec(
            item_spec_id=ItemSpecId(13),
            name="Iron Armor",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="Protects the body",
            max_stack_size=MaxStackSize(1),
            equipment_type=EquipmentType.ARMOR
        )
        assert armor_spec.equipment_type == EquipmentType.ARMOR
        assert armor_spec.is_equipment()

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
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="A test sword for testing",
            max_stack_size=MaxStackSize(64),
            equipment_type=EquipmentType.WEAPON
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
            # equipment_type=None (デフォルト値) - CONSUMABLEなのでNoneでOK
        )

        assert hash(sample_item_spec) == hash(same_spec)

        # setで重複を除去できる
        specs = {sample_item_spec, same_spec}
        assert len(specs) == 1

    def test_immutable(self, sample_item_spec):
        """不変性のテスト"""
        with pytest.raises(AttributeError):
            sample_item_spec.name = "New Name"


class TestItemSpecPlaceable:
    """ItemSpec 設置可能フラグと placeable_object_type のバリデーション"""

    @pytest.fixture
    def base_spec_params(self):
        return {
            "item_spec_id": ItemSpecId(100),
            "name": "Placeable Chest",
            "item_type": ItemType.OTHER,
            "rarity": Rarity.COMMON,
            "description": "A placeable chest",
            "max_stack_size": MaxStackSize(1),
        }

    def test_placeable_with_valid_object_type(self, base_spec_params):
        """設置可能で placeable_object_type が有効な値のとき作成できる"""
        spec = ItemSpec(**base_spec_params, is_placeable=True, placeable_object_type="CHEST")
        assert spec.is_placeable_item() is True
        assert spec.get_placeable_object_type() == "CHEST"

    def test_placeable_doer_sign_switch(self, base_spec_params):
        """DOOR, SIGN, SWITCH も有効な設置先として作成できる"""
        for obj_type in ("DOOR", "SIGN", "SWITCH", "GATE"):
            spec = ItemSpec(**base_spec_params, is_placeable=True, placeable_object_type=obj_type)
            assert spec.get_placeable_object_type() == obj_type

    def test_non_placeable_default(self, base_spec_params):
        """デフォルトは設置不可・placeable_object_type は None"""
        spec = ItemSpec(**base_spec_params)
        assert spec.is_placeable_item() is False
        assert spec.get_placeable_object_type() is None

    def test_placeable_without_object_type_raises(self, base_spec_params):
        """設置可能なのに placeable_object_type が未設定ならバリデーションエラー"""
        with pytest.raises(ItemSpecValidationException) as exc_info:
            ItemSpec(**base_spec_params, is_placeable=True, placeable_object_type=None)
        assert "placeable items must have placeable_object_type" in str(exc_info.value)

    def test_placeable_with_empty_object_type_raises(self, base_spec_params):
        """設置可能なのに placeable_object_type が空文字ならバリデーションエラー"""
        with pytest.raises(ItemSpecValidationException):
            ItemSpec(**base_spec_params, is_placeable=True, placeable_object_type="")

    def test_placeable_with_invalid_object_type_raises(self, base_spec_params):
        """設置可能なのに許可されていない placeable_object_type ならバリデーションエラー"""
        with pytest.raises(ItemSpecValidationException) as exc_info:
            ItemSpec(**base_spec_params, is_placeable=True, placeable_object_type="INVALID_TYPE")
        assert "placeable_object_type must be one of" in str(exc_info.value)

    def test_non_placeable_with_object_type_raises(self, base_spec_params):
        """設置不可なのに placeable_object_type が設定されていればバリデーションエラー"""
        with pytest.raises(ItemSpecValidationException) as exc_info:
            ItemSpec(**base_spec_params, is_placeable=False, placeable_object_type="CHEST")
        assert "non-placeable items must not have placeable_object_type" in str(exc_info.value)
