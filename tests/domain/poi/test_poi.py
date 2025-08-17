import pytest
from unittest.mock import Mock

from src.domain.poi.poi import POI, POIUnlockCondition, POIReward
from src.domain.poi.poi_enum import POIType


class TestPOIUnlockCondition:
    """POIUnlockConditionクラスのテスト"""
    
    def test_no_conditions_always_satisfied(self):
        """条件なしの場合は常に満たされる"""
        condition = POIUnlockCondition()
        mock_player = Mock()
        discovered_pois = set()
        
        assert condition.is_satisfied(mock_player, discovered_pois) is True
    
    def test_required_items_satisfied(self):
        """必要アイテムの条件が満たされる場合"""
        condition = POIUnlockCondition(required_items={1, 2})
        mock_player = Mock()
        mock_player.has_item.side_effect = lambda item_id: item_id in {1, 2}
        discovered_pois = set()
        
        assert condition.is_satisfied(mock_player, discovered_pois) is True
    
    def test_required_items_not_satisfied(self):
        """必要アイテムの条件が満たされない場合"""
        condition = POIUnlockCondition(required_items={1, 2})
        mock_player = Mock()
        mock_player.has_item.side_effect = lambda item_id: item_id == 1  # 2がない
        discovered_pois = set()
        
        assert condition.is_satisfied(mock_player, discovered_pois) is False
    
    def test_required_poi_discoveries_satisfied(self):
        """必要POI発見条件が満たされる場合"""
        condition = POIUnlockCondition(required_poi_discoveries={10, 20})
        mock_player = Mock()
        discovered_pois = {10, 20, 30}
        
        assert condition.is_satisfied(mock_player, discovered_pois) is True
    
    def test_required_poi_discoveries_not_satisfied(self):
        """必要POI発見条件が満たされない場合"""
        condition = POIUnlockCondition(required_poi_discoveries={10, 20})
        mock_player = Mock()
        discovered_pois = {10}  # 20がない
        
        assert condition.is_satisfied(mock_player, discovered_pois) is False
    
    def test_both_conditions_satisfied(self):
        """アイテムとPOI発見の両方の条件が満たされる場合"""
        condition = POIUnlockCondition(
            required_items={1},
            required_poi_discoveries={10}
        )
        mock_player = Mock()
        mock_player.has_item.return_value = True
        discovered_pois = {10}
        
        assert condition.is_satisfied(mock_player, discovered_pois) is True
    
    def test_mixed_conditions_partial_satisfied(self):
        """複合条件で一部のみ満たされる場合"""
        condition = POIUnlockCondition(
            required_items={1},
            required_poi_discoveries={10}
        )
        mock_player = Mock()
        mock_player.has_item.return_value = True
        discovered_pois = set()  # POI条件が満たされない
        
        assert condition.is_satisfied(mock_player, discovered_pois) is False


class TestPOIReward:
    """POIRewardクラスのテスト"""
    
    def test_default_reward_creation(self):
        """デフォルト報酬の作成"""
        reward = POIReward()
        assert reward.information == ""
        assert reward.gold == 0
        assert reward.exp == 0
        assert reward.items == []
    
    def test_custom_reward_creation(self):
        """カスタム報酬の作成"""
        reward = POIReward(
            information="古い宝の地図を発見した",
            gold=100,
            exp=50,
            items=[1, 2, 3]
        )
        assert reward.information == "古い宝の地図を発見した"
        assert reward.gold == 100
        assert reward.exp == 50
        assert reward.items == [1, 2, 3]
    
    def test_invalid_gold_negative(self):
        """金額が負の場合のエラー"""
        with pytest.raises(ValueError, match="Gold must be greater than 0"):
            POIReward(gold=-1)
    
    def test_invalid_exp_negative(self):
        """経験値が負の場合のエラー"""
        with pytest.raises(ValueError, match="Exp must be greater than 0"):
            POIReward(exp=-1)
    
    def test_none_items_list_initialization(self):
        """Noneのアイテムリストが空リストに初期化される"""
        reward = POIReward(items=None)
        assert reward.items == []


class TestPOI:
    """POIクラスのテスト"""
    
    @pytest.fixture
    def sample_poi(self):
        """テスト用POIサンプル"""
        condition = POIUnlockCondition(required_items={1})
        reward = POIReward(information="宝箱を発見", gold=100, exp=50)
        return POI(
            poi_id="treasure_1",
            name="古い宝箱",
            description="苔むした古い宝箱が隠されている",
            poi_type=POIType.TREASURE,
            unlock_condition=condition,
            reward=reward
        )
    
    def test_poi_creation(self, sample_poi):
        """POIの作成"""
        assert sample_poi._poi_id == "treasure_1"
        assert sample_poi._name == "古い宝箱"
        assert sample_poi._description == "苔むした古い宝箱が隠されている"
        assert sample_poi._poi_type == POIType.TREASURE
        assert isinstance(sample_poi._unlock_condition, POIUnlockCondition)
        assert isinstance(sample_poi._reward, POIReward)
    
    def test_can_explore_true(self, sample_poi):
        """探索可能性判定 - True"""
        mock_player = Mock()
        mock_player.has_item.return_value = True
        discovered_pois = set()
        
        assert sample_poi.can_explore(mock_player, discovered_pois) is True
    
    def test_can_explore_false(self, sample_poi):
        """探索可能性判定 - False"""
        mock_player = Mock()
        mock_player.has_item.return_value = False
        discovered_pois = set()
        
        assert sample_poi.can_explore(mock_player, discovered_pois) is False
    
    def test_explore_returns_reward(self, sample_poi):
        """探索実行で報酬が返される"""
        reward = sample_poi.explore()
        
        assert isinstance(reward, POIReward)
        assert reward.information == "宝箱を発見"
        assert reward.gold == 100
        assert reward.exp == 50
    
    def test_different_poi_types(self):
        """異なるPOIタイプでの作成"""
        condition = POIUnlockCondition()
        reward = POIReward()
        
        # MONSTER_LAIR
        monster_poi = POI(
            poi_id="monster_1",
            name="怪物の巣",
            description="恐ろしい怪物が潜んでいる",
            poi_type=POIType.MONSTER_LAIR,
            unlock_condition=condition,
            reward=reward
        )
        assert monster_poi._poi_type == POIType.MONSTER_LAIR
        
        # SECRET_PASSAGE
        secret_poi = POI(
            poi_id="secret_1",
            name="隠し通路",
            description="秘密の通路への入り口",
            poi_type=POIType.SECRET_PASSAGE,
            unlock_condition=condition,
            reward=reward
        )
        assert secret_poi._poi_type == POIType.SECRET_PASSAGE
        
        # INFORMATION
        info_poi = POI(
            poi_id="info_1",
            name="古い石碑",
            description="古代文字が刻まれた石碑",
            poi_type=POIType.INFORMATION,
            unlock_condition=condition,
            reward=reward
        )
        assert info_poi._poi_type == POIType.INFORMATION
    
    def test_complex_unlock_conditions(self):
        """複雑なアンロック条件のテスト"""
        condition = POIUnlockCondition(
            required_items={1, 2, 3},
            required_poi_discoveries={10, 20}
        )
        reward = POIReward(information="秘密を発見")
        poi = POI(
            poi_id="complex_1",
            name="秘密の部屋",
            description="複雑な条件で開く秘密の部屋",
            poi_type=POIType.SECRET_PASSAGE,
            unlock_condition=condition,
            reward=reward
        )
        
        # 条件を満たさない場合
        mock_player = Mock()
        mock_player.has_item.side_effect = lambda item_id: item_id in {1, 2}  # 3がない
        discovered_pois = {10, 20}
        assert poi.can_explore(mock_player, discovered_pois) is False
        
        # 条件を満たす場合
        mock_player.has_item.side_effect = lambda item_id: item_id in {1, 2, 3}
        assert poi.can_explore(mock_player, discovered_pois) is True
