import pytest
from src.domain.spot.road import Road
from src.domain.spot.condition import LevelConditionChecker, ItemConditionChecker, GoldConditionChecker, RoleConditionChecker
from src.domain.player.level import Level
from src.domain.player.gold import Gold
from src.domain.player.player_enum import Role
from src.domain.spot.spot_exception import PlayerNotMeetConditionException


class TestRoad:
    """Roadドメインモデルのテストクラス"""

    def test_road_initialization(self):
        """Roadの初期化テスト"""
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道"
        )
        
        assert road.road_id == 1
        assert road.from_spot_id == 10
        assert road.to_spot_id == 20
        assert road.description == "森への道"
        assert road.conditions is None

    def test_road_initialization_with_conditions(self):
        """条件付きRoadの初期化テスト"""
        level_condition = LevelConditionChecker(5)
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道",
            conditions=level_condition
        )
        
        assert road.road_id == 1
        assert road.from_spot_id == 10
        assert road.to_spot_id == 20
        assert road.description == "森への道"
        assert road.conditions == level_condition

    def test_create_inverse_road(self):
        """逆方向の道路作成テスト"""
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道"
        )
        
        inverse_road = road.create_inverse_road(
            road_id=2,
            description="町への道"
        )
        
        assert inverse_road.road_id == 2
        assert inverse_road.from_spot_id == 20  # 逆方向
        assert inverse_road.to_spot_id == 10    # 逆方向
        assert inverse_road.description == "町への道"
        assert inverse_road.conditions is None

    def test_create_inverse_road_with_conditions(self):
        """条件付き逆方向道路作成テスト"""
        level_condition = LevelConditionChecker(5)
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道",
            conditions=level_condition
        )
        
        inverse_condition = LevelConditionChecker(3)
        inverse_road = road.create_inverse_road(
            road_id=2,
            description="町への道",
            conditions=inverse_condition
        )
        
        assert inverse_road.road_id == 2
        assert inverse_road.from_spot_id == 20
        assert inverse_road.to_spot_id == 10
        assert inverse_road.description == "町への道"
        assert inverse_road.conditions == inverse_condition

    def test_create_inverse_road_same_id_raises_exception(self):
        """同じIDでの逆方向道路作成で例外が発生するテスト"""
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道"
        )
        
        with pytest.raises(ValueError) as exc_info:
            road.create_inverse_road(road_id=1, description="町への道")
        
        assert "Road 1 is the same as the original road" in str(exc_info.value)

    def test_check_player_conditions_no_conditions(self):
        """条件なしの場合のプレイヤー条件チェックテスト"""
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道"
        )
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id):
                self.player_id = player_id
        
        player = MockPlayer(100)
        
        # 条件がない場合は例外が発生しない
        road.check_player_conditions(player)

    def test_check_player_conditions_with_level_condition(self):
        """レベル条件付きのプレイヤー条件チェックテスト"""
        level_condition = LevelConditionChecker(5)
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道",
            conditions=level_condition
        )
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, level):
                self.player_id = player_id
                self._level = level
            
            def level_is_above(self, required_level):
                return self._level >= required_level.value
        
        # 条件を満たすプレイヤー
        high_level_player = MockPlayer(100, 7)
        road.check_player_conditions(high_level_player)  # 例外が発生しない
        
        # 条件を満たさないプレイヤー
        low_level_player = MockPlayer(200, 3)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            road.check_player_conditions(low_level_player)
        
        assert "Player 200 does not meet the level condition: 5" in str(exc_info.value)

    def test_check_player_conditions_with_item_condition(self):
        """アイテム条件付きのプレイヤー条件チェックテスト"""
        item_condition = ItemConditionChecker(item_id=100, quantity=2)
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道",
            conditions=item_condition
        )
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, has_item):
                self.player_id = player_id
                self._has_item = has_item
            
            def has_item(self, item_id, quantity):
                return self._has_item
        
        # 条件を満たすプレイヤー
        player_with_item = MockPlayer(100, True)
        road.check_player_conditions(player_with_item)  # 例外が発生しない
        
        # 条件を満たさないプレイヤー
        player_without_item = MockPlayer(200, False)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            road.check_player_conditions(player_without_item)
        
        assert "Player 200 does not meet the item condition: 100 2" in str(exc_info.value)

    def test_check_player_conditions_with_gold_condition(self):
        """ゴールド条件付きのプレイヤー条件チェックテスト"""
        gold_condition = GoldConditionChecker(1000)
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道",
            conditions=gold_condition
        )
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, can_pay):
                self.player_id = player_id
                self._can_pay = can_pay
            
            def can_pay_gold(self, gold):
                return self._can_pay
        
        # 条件を満たすプレイヤー
        rich_player = MockPlayer(100, True)
        road.check_player_conditions(rich_player)  # 例外が発生しない
        
        # 条件を満たさないプレイヤー
        poor_player = MockPlayer(200, False)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            road.check_player_conditions(poor_player)
        
        assert "Player 200 does not meet the gold condition: 1000" in str(exc_info.value)

    def test_check_player_conditions_with_role_condition(self):
        """役職条件付きのプレイヤー条件チェックテスト"""
        role_condition = RoleConditionChecker(Role.ADVENTURER)
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道",
            conditions=role_condition
        )
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, is_adventurer):
                self.player_id = player_id
                self._is_adventurer = is_adventurer
            
            def is_role(self, role):
                return self._is_adventurer and role == Role.ADVENTURER
        
        # 条件を満たすプレイヤー
        adventurer_player = MockPlayer(100, True)
        road.check_player_conditions(adventurer_player)  # 例外が発生しない
        
        # 条件を満たさないプレイヤー
        non_adventurer_player = MockPlayer(200, False)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            road.check_player_conditions(non_adventurer_player)
        
        assert "Player 200 does not meet the role condition: Role.ADVENTURER" in str(exc_info.value)
