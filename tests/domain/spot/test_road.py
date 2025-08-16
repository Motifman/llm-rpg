import pytest
from src.domain.spot.road import Road, Condition, ConditionCheckResult
from src.domain.spot.road_enum import ConditionType
from src.domain.player.player_enum import Role
from src.domain.player.player import Player
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.conversation.message_box import MessageBox


class TestCondition:
    def test_condition_creation_min_level(self):
        """MIN_LEVELの条件作成テスト"""
        condition = Condition(ConditionType.MIN_LEVEL, 5)
        assert condition.condition_type == ConditionType.MIN_LEVEL
        assert condition.value == 5
    
    def test_condition_creation_has_gold(self):
        """HAS_GOLDの条件作成テスト"""
        condition = Condition(ConditionType.HAS_GOLD, 100)
        assert condition.condition_type == ConditionType.HAS_GOLD
        assert condition.value == 100
    
    def test_condition_creation_has_item(self):
        """HAS_ITEMの条件作成テスト"""
        condition = Condition(ConditionType.HAS_ITEM, 1001)
        assert condition.condition_type == ConditionType.HAS_ITEM
        assert condition.value == 1001
    
    def test_condition_creation_has_role(self):
        """HAS_ROLEの条件作成テスト"""
        condition = Condition(ConditionType.HAS_ROLE, Role.ADVENTURER)
        assert condition.condition_type == ConditionType.HAS_ROLE
        assert condition.value == Role.ADVENTURER
    
    def test_condition_creation_invalid_negative_gold(self):
        """負のゴールド値で例外が発生するテスト"""
        with pytest.raises(ValueError):
            Condition(ConditionType.HAS_GOLD, -1)
    
    def test_condition_creation_invalid_negative_level(self):
        """負のレベル値で例外が発生するテスト"""
        with pytest.raises(ValueError):
            Condition(ConditionType.MIN_LEVEL, -1)
    
    def test_condition_creation_invalid_negative_item(self):
        """負のアイテムIDで例外が発生するテスト"""
        with pytest.raises(ValueError):
            Condition(ConditionType.HAS_ITEM, -1)
    
    def test_condition_creation_invalid_none_role(self):
        """Noneのロール値で例外が発生するテスト"""
        with pytest.raises(ValueError):
            Condition(ConditionType.HAS_ROLE, None)


@pytest.fixture
def mock_player():
    """テスト用のプレイヤーオブジェクトを作成"""
    base_status = BaseStatus(
        attack=20, defense=10, speed=15, critical_rate=0.1, evasion_rate=0.05
    )
    dynamic_status = DynamicStatus(
        hp=100, mp=50, max_hp=100, max_mp=50, exp=250, level=5, gold=150
    )
    inventory = Inventory()
    equipment_set = EquipmentSet()
    message_box = MessageBox()
    
    return Player(
        player_id=1,
        name="TestPlayer",
        role=Role.ADVENTURER,
        current_spot_id=1,
        base_status=base_status,
        dynamic_status=dynamic_status,
        inventory=inventory,
        equipment_set=equipment_set,
        message_box=message_box
    )


class TestConditionCheck:
    def test_min_level_condition_satisfied(self, mock_player):
        """レベル条件が満たされている場合のテスト"""
        condition = Condition(ConditionType.MIN_LEVEL, 3)
        assert condition.check(mock_player) is True
    
    def test_min_level_condition_not_satisfied(self, mock_player):
        """レベル条件が満たされていない場合のテスト"""
        condition = Condition(ConditionType.MIN_LEVEL, 10)
        assert condition.check(mock_player) is False
    
    def test_has_gold_condition_satisfied(self, mock_player):
        """ゴールド条件が満たされている場合のテスト"""
        condition = Condition(ConditionType.HAS_GOLD, 100)
        assert condition.check(mock_player) is True
    
    def test_has_gold_condition_not_satisfied(self, mock_player):
        """ゴールド条件が満たされていない場合のテスト"""
        condition = Condition(ConditionType.HAS_GOLD, 200)
        assert condition.check(mock_player) is False
    
    def test_has_role_condition_satisfied(self, mock_player):
        """ロール条件が満たされている場合のテスト"""
        condition = Condition(ConditionType.HAS_ROLE, Role.ADVENTURER)
        assert condition.check(mock_player) is True
    
    def test_has_role_condition_not_satisfied(self, mock_player):
        """ロール条件が満たされていない場合のテスト"""
        condition = Condition(ConditionType.HAS_ROLE, Role.MERCHANT)
        assert condition.check(mock_player) is False


class TestConditionCheckWithDetails:
    def test_min_level_condition_details_satisfied(self, mock_player):
        """レベル条件の詳細チェック（満たされている場合）"""
        condition = Condition(ConditionType.MIN_LEVEL, 3)
        result = condition.check_with_details(mock_player)
        
        assert isinstance(result, ConditionCheckResult)
        assert result.condition == condition
        assert result.is_satisfied is True
        assert "レベル 3 以上が必要" in result.message
        assert "現在: 5" in result.message
    
    def test_min_level_condition_details_not_satisfied(self, mock_player):
        """レベル条件の詳細チェック（満たされていない場合）"""
        condition = Condition(ConditionType.MIN_LEVEL, 10)
        result = condition.check_with_details(mock_player)
        
        assert isinstance(result, ConditionCheckResult)
        assert result.condition == condition
        assert result.is_satisfied is False
        assert "レベル 10 以上が必要" in result.message
        assert "現在: 5" in result.message
    
    def test_has_gold_condition_details_satisfied(self, mock_player):
        """ゴールド条件の詳細チェック（満たされている場合）"""
        condition = Condition(ConditionType.HAS_GOLD, 100)
        result = condition.check_with_details(mock_player)
        
        assert isinstance(result, ConditionCheckResult)
        assert result.condition == condition
        assert result.is_satisfied is True
        assert "ゴールド 100 以上が必要" in result.message
        assert "現在: 150" in result.message
    
    def test_has_gold_condition_details_not_satisfied(self, mock_player):
        """ゴールド条件の詳細チェック（満たされていない場合）"""
        condition = Condition(ConditionType.HAS_GOLD, 200)
        result = condition.check_with_details(mock_player)
        
        assert isinstance(result, ConditionCheckResult)
        assert result.condition == condition
        assert result.is_satisfied is False
        assert "ゴールド 200 以上が必要" in result.message
        assert "現在: 150" in result.message


class TestRoad:
    def test_road_creation_basic(self):
        """基本的な道路作成テスト"""
        road = Road(
            road_id=1,
            from_spot_id=1,
            from_spot_name="町の入り口",
            to_spot_id=2,
            to_spot_name="市場",
            description="町の入り口から市場への道"
        )
        
        assert road.road_id == 1
        assert road.from_spot_id == 1
        assert road.from_spot_name == "町の入り口"
        assert road.to_spot_id == 2
        assert road.to_spot_name == "市場"
        assert road.description == "町の入り口から市場への道"
        assert road.conditions == []
    
    def test_road_creation_with_conditions(self):
        """条件付き道路作成テスト"""
        conditions = [
            Condition(ConditionType.MIN_LEVEL, 5),
            Condition(ConditionType.HAS_GOLD, 100)
        ]
        road = Road(
            road_id=2,
            from_spot_id=2,
            from_spot_name="市場",
            to_spot_id=3,
            to_spot_name="冒険者ギルド",
            description="市場から冒険者ギルドへの道",
            conditions=conditions
        )
        
        assert road.road_id == 2
        assert len(road.conditions) == 2
        assert road.conditions[0].condition_type == ConditionType.MIN_LEVEL
        assert road.conditions[1].condition_type == ConditionType.HAS_GOLD
    
    def test_create_inverse_road(self):
        """逆方向の道路作成テスト"""
        original_road = Road(
            road_id=1,
            from_spot_id=1,
            from_spot_name="町の入り口",
            to_spot_id=2,
            to_spot_name="市場",
            description="町の入り口から市場への道"
        )
        
        inverse_conditions = [Condition(ConditionType.HAS_GOLD, 50)]
        inverse_road = original_road.create_inverse_road(
            road_id=2,
            description="市場から町の入り口への道",
            conditions=inverse_conditions
        )
        
        assert inverse_road.road_id == 2
        assert inverse_road.from_spot_id == 2
        assert inverse_road.from_spot_name == "市場"
        assert inverse_road.to_spot_id == 1
        assert inverse_road.to_spot_name == "町の入り口"
        assert inverse_road.description == "市場から町の入り口への道"
        assert len(inverse_road.conditions) == 1
    
    def test_create_inverse_road_same_id_error(self):
        """同じIDで逆方向道路作成時のエラーテスト"""
        road = Road(
            road_id=1,
            from_spot_id=1,
            from_spot_name="町の入り口",
            to_spot_id=2,
            to_spot_name="市場",
            description="町の入り口から市場への道"
        )
        
        with pytest.raises(ValueError):
            road.create_inverse_road(road_id=1, description="同じIDの道路")
    
    def test_is_available_no_conditions(self, mock_player):
        """条件なしの道路利用可能性テスト"""
        road = Road(
            road_id=1,
            from_spot_id=1,
            from_spot_name="町の入り口",
            to_spot_id=2,
            to_spot_name="市場",
            description="町の入り口から市場への道"
        )
        
        assert road.is_available(mock_player) is True
    
    def test_is_available_all_conditions_satisfied(self, mock_player):
        """すべての条件が満たされた場合の利用可能性テスト"""
        conditions = [
            Condition(ConditionType.MIN_LEVEL, 3),
            Condition(ConditionType.HAS_GOLD, 100),
            Condition(ConditionType.HAS_ROLE, Role.ADVENTURER)
        ]
        road = Road(
            road_id=2,
            from_spot_id=2,
            from_spot_name="市場",
            to_spot_id=3,
            to_spot_name="冒険者ギルド",
            description="市場から冒険者ギルドへの道",
            conditions=conditions
        )
        
        assert road.is_available(mock_player) is True
    
    def test_is_available_some_conditions_not_satisfied(self, mock_player):
        """一部の条件が満たされていない場合の利用可能性テスト"""
        conditions = [
            Condition(ConditionType.MIN_LEVEL, 3),  # 満たされる
            Condition(ConditionType.HAS_GOLD, 200)  # 満たされない（プレイヤーは150ゴールド）
        ]
        road = Road(
            road_id=3,
            from_spot_id=3,
            from_spot_name="冒険者ギルド",
            to_spot_id=4,
            to_spot_name="王城",
            description="冒険者ギルドから王城への道",
            conditions=conditions
        )
        
        assert road.is_available(mock_player) is False
    
    def test_get_availability_message_available(self, mock_player):
        """利用可能な場合のメッセージテスト"""
        road = Road(
            road_id=1,
            from_spot_id=1,
            from_spot_name="町の入り口",
            to_spot_id=2,
            to_spot_name="市場",
            description="町の入り口から市場への道"
        )
        
        message = road.get_availability_message(mock_player)
        assert "利用可能です" in message
        assert "町の入り口から市場への道" in message
    
    def test_get_availability_message_not_available(self, mock_player):
        """利用不可能な場合のメッセージテスト"""
        conditions = [
            Condition(ConditionType.MIN_LEVEL, 10),  # 満たされない
            Condition(ConditionType.HAS_GOLD, 200)   # 満たされない
        ]
        road = Road(
            road_id=4,
            from_spot_id=4,
            from_spot_name="王城",
            to_spot_id=5,
            to_spot_name="秘密の部屋",
            description="王城から秘密の部屋への道",
            conditions=conditions
        )
        
        message = road.get_availability_message(mock_player)
        assert "利用できません" in message
        assert "王城から秘密の部屋への道" in message
        assert "レベル 10 以上が必要" in message
        assert "ゴールド 200 以上が必要" in message
