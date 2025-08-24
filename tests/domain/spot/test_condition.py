import pytest
from src.domain.spot.condition import (
    ConditionChecker,
    LevelConditionChecker,
    ItemConditionChecker,
    GoldConditionChecker,
    RoleConditionChecker,
    CompositeConditionChecker
)
from src.domain.player.level import Level
from src.domain.player.gold import Gold
from src.domain.player.player_enum import Role
from src.domain.spot.spot_exception import PlayerNotMeetConditionException


class TestLevelConditionChecker:
    """レベル条件チェッカーのテストクラス"""

    def test_level_condition_initialization(self):
        """レベル条件の初期化テスト"""
        level_condition = LevelConditionChecker(5)
        assert level_condition.level == Level(5)

    def test_level_condition_check_success(self):
        """レベル条件チェック成功テスト"""
        level_condition = LevelConditionChecker(5)
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, level):
                self.player_id = player_id
                self._level = level
            
            def level_is_above(self, required_level):
                return self._level >= required_level.value
        
        # 条件を満たすプレイヤー
        high_level_player = MockPlayer(100, 7)
        level_condition.check(high_level_player)  # 例外が発生しない

    def test_level_condition_check_failure(self):
        """レベル条件チェック失敗テスト"""
        level_condition = LevelConditionChecker(5)
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, level):
                self.player_id = player_id
                self._level = level
            
            def level_is_above(self, required_level):
                return self._level >= required_level.value
        
        # 条件を満たさないプレイヤー
        low_level_player = MockPlayer(200, 3)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            level_condition.check(low_level_player)
        
        assert "Player 200 does not meet the level condition: 5" in str(exc_info.value)


class TestItemConditionChecker:
    """アイテム条件チェッカーのテストクラス"""

    def test_item_condition_initialization(self):
        """アイテム条件の初期化テスト"""
        item_condition = ItemConditionChecker(item_id=100, quantity=2)
        assert item_condition.item_id == 100
        assert item_condition.quantity == 2

    def test_item_condition_check_success(self):
        """アイテム条件チェック成功テスト"""
        item_condition = ItemConditionChecker(item_id=100, quantity=2)
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, has_item):
                self.player_id = player_id
                self._has_item = has_item
            
            def has_item(self, item_id, quantity):
                return self._has_item
        
        # 条件を満たすプレイヤー
        player_with_item = MockPlayer(100, True)
        item_condition.check(player_with_item)  # 例外が発生しない

    def test_item_condition_check_failure(self):
        """アイテム条件チェック失敗テスト"""
        item_condition = ItemConditionChecker(item_id=100, quantity=2)
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, has_item):
                self.player_id = player_id
                self._has_item = has_item
            
            def has_item(self, item_id, quantity):
                return self._has_item
        
        # 条件を満たさないプレイヤー
        player_without_item = MockPlayer(200, False)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            item_condition.check(player_without_item)
        
        assert "Player 200 does not meet the item condition: 100 2" in str(exc_info.value)


class TestGoldConditionChecker:
    """ゴールド条件チェッカーのテストクラス"""

    def test_gold_condition_initialization(self):
        """ゴールド条件の初期化テスト"""
        gold_condition = GoldConditionChecker(1000)
        assert gold_condition.gold == Gold(1000)

    def test_gold_condition_check_success(self):
        """ゴールド条件チェック成功テスト"""
        gold_condition = GoldConditionChecker(1000)
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, can_pay):
                self.player_id = player_id
                self._can_pay = can_pay
            
            def can_pay_gold(self, gold):
                return self._can_pay
        
        # 条件を満たすプレイヤー
        rich_player = MockPlayer(100, True)
        gold_condition.check(rich_player)  # 例外が発生しない

    def test_gold_condition_check_failure(self):
        """ゴールド条件チェック失敗テスト"""
        gold_condition = GoldConditionChecker(1000)
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, can_pay):
                self.player_id = player_id
                self._can_pay = can_pay
            
            def can_pay_gold(self, gold):
                return self._can_pay
        
        # 条件を満たさないプレイヤー
        poor_player = MockPlayer(200, False)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            gold_condition.check(poor_player)
        
        assert "Player 200 does not meet the gold condition: 1000" in str(exc_info.value)


class TestRoleConditionChecker:
    """役職条件チェッカーのテストクラス"""

    def test_role_condition_initialization(self):
        """役職条件の初期化テスト"""
        role_condition = RoleConditionChecker(Role.ADVENTURER)
        assert role_condition.role == Role.ADVENTURER

    def test_role_condition_check_success(self):
        """役職条件チェック成功テスト"""
        role_condition = RoleConditionChecker(Role.ADVENTURER)
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, is_adventurer):
                self.player_id = player_id
                self._is_adventurer = is_adventurer
            
            def is_role(self, role):
                return self._is_adventurer and role == Role.ADVENTURER
        
        # 条件を満たすプレイヤー
        adventurer_player = MockPlayer(100, True)
        role_condition.check(adventurer_player)  # 例外が発生しない

    def test_role_condition_check_failure(self):
        """役職条件チェック失敗テスト"""
        role_condition = RoleConditionChecker(Role.ADVENTURER)
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, is_adventurer):
                self.player_id = player_id
                self._is_adventurer = is_adventurer
            
            def is_role(self, role):
                return self._is_adventurer and role == Role.ADVENTURER
        
        # 条件を満たさないプレイヤー
        non_adventurer_player = MockPlayer(200, False)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            role_condition.check(non_adventurer_player)
        
        assert "Player 200 does not meet the role condition: Role.ADVENTURER" in str(exc_info.value)


class TestCompositeConditionChecker:
    """複合条件チェッカーのテストクラス"""

    def test_composite_condition_initialization(self):
        """複合条件の初期化テスト"""
        level_condition = LevelConditionChecker(5)
        item_condition = ItemConditionChecker(item_id=100, quantity=1)
        composite_condition = CompositeConditionChecker([level_condition, item_condition])
        
        assert len(composite_condition.conditions) == 2
        assert composite_condition.conditions[0] == level_condition
        assert composite_condition.conditions[1] == item_condition

    def test_composite_condition_check_success(self):
        """複合条件チェック成功テスト"""
        level_condition = LevelConditionChecker(5)
        item_condition = ItemConditionChecker(item_id=100, quantity=1)
        composite_condition = CompositeConditionChecker([level_condition, item_condition])
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, level, has_item):
                self.player_id = player_id
                self._level = level
                self._has_item = has_item
            
            def level_is_above(self, required_level):
                return self._level >= required_level.value
            
            def has_item(self, item_id, quantity):
                return self._has_item
        
        # 両方の条件を満たすプレイヤー
        qualified_player = MockPlayer(100, 7, True)
        composite_condition.check(qualified_player)  # 例外が発生しない

    def test_composite_condition_check_first_condition_failure(self):
        """複合条件チェック - 最初の条件失敗テスト"""
        level_condition = LevelConditionChecker(5)
        item_condition = ItemConditionChecker(item_id=100, quantity=1)
        composite_condition = CompositeConditionChecker([level_condition, item_condition])
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, level, has_item):
                self.player_id = player_id
                self._level = level
                self._has_item = has_item
            
            def level_is_above(self, required_level):
                return self._level >= required_level.value
            
            def has_item(self, item_id, quantity):
                return self._has_item
        
        # レベル条件を満たさないプレイヤー
        low_level_player = MockPlayer(200, 3, True)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            composite_condition.check(low_level_player)
        
        assert "Player 200 does not meet the level condition: 5" in str(exc_info.value)

    def test_composite_condition_check_second_condition_failure(self):
        """複合条件チェック - 2番目の条件失敗テスト"""
        level_condition = LevelConditionChecker(5)
        item_condition = ItemConditionChecker(item_id=100, quantity=1)
        composite_condition = CompositeConditionChecker([level_condition, item_condition])
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, level, has_item):
                self.player_id = player_id
                self._level = level
                self._has_item = has_item
            
            def level_is_above(self, required_level):
                return self._level >= required_level.value
            
            def has_item(self, item_id, quantity):
                return self._has_item
        
        # アイテム条件を満たさないプレイヤー
        no_item_player = MockPlayer(300, 7, False)
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            composite_condition.check(no_item_player)
        
        assert "Player 300 does not meet the item condition: 100 1" in str(exc_info.value)

    def test_composite_condition_empty_list(self):
        """空の条件リストでの複合条件テスト"""
        composite_condition = CompositeConditionChecker([])
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id):
                self.player_id = player_id
        
        player = MockPlayer(100)
        composite_condition.check(player)  # 例外が発生しない
