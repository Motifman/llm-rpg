import pytest
from unittest.mock import Mock
from datetime import datetime

from src.domain.poi.poi import POI, POIUnlockCondition, POIReward
from src.domain.poi.poi_enum import POIType
from src.domain.poi.poi_exploration import POIExploration, POIExplorationResult


class TestPOIExplorationResult:
    """POIExplorationResultクラスのテスト"""
    
    def test_exploration_result_creation(self):
        """探索結果の作成"""
        reward = POIReward(information="宝を発見", gold=100)
        timestamp = datetime(2023, 1, 1, 12, 0, 0)
        
        result = POIExplorationResult(
            poi_id=1,
            success=True,
            reward=reward,
            timestamp=timestamp
        )
        
        assert result.poi_id == 1
        assert result.success is True
        assert result.reward == reward
        assert result.timestamp == timestamp
    
    def test_failed_exploration_result(self):
        """失敗した探索結果"""
        empty_reward = POIReward()
        timestamp = datetime(2023, 1, 1, 12, 0, 0)
        
        result = POIExplorationResult(
            poi_id=2,
            success=False,
            reward=empty_reward,
            timestamp=timestamp
        )
        
        assert result.poi_id == 2
        assert result.success is False
        assert result.reward.gold == 0
        assert result.reward.exp == 0
        assert result.reward.information == ""
        assert result.reward.items == []


class TestPOIExploration:
    """POIExplorationクラスのテスト"""
    
    @pytest.fixture
    def poi_exploration(self):
        """POI探索サービスのインスタンス"""
        return POIExploration()
    
    @pytest.fixture
    def sample_poi(self):
        """テスト用POI"""
        condition = POIUnlockCondition(required_items={1})
        reward = POIReward(information="古い宝箱を発見", gold=200, exp=100, items=[5, 6])
        return POI(
            poi_id=3,
            name="古い宝箱",
            description="苔むした宝箱",
            poi_type=POIType.TREASURE,
            unlock_condition=condition,
            reward=reward
        )
    
    def test_successful_exploration(self, poi_exploration, sample_poi):
        """成功した探索"""
        mock_player = Mock()
        mock_player.has_item.return_value = True
        discovered_pois = set()
        
        result = poi_exploration.explore_poi(sample_poi, mock_player, discovered_pois)
        
        assert isinstance(result, POIExplorationResult)
        assert result.poi_id == 3
        assert result.success is True
        assert result.reward.information == "古い宝箱を発見"
        assert result.reward.gold == 200
        assert result.reward.exp == 100
        assert result.reward.items == [5, 6]
        assert isinstance(result.timestamp, datetime)
    
    def test_failed_exploration_due_to_conditions(self, poi_exploration, sample_poi):
        """条件不足による探索失敗"""
        mock_player = Mock()
        mock_player.has_item.return_value = False  # 必要アイテムを持っていない
        discovered_pois = set()
        
        result = poi_exploration.explore_poi(sample_poi, mock_player, discovered_pois)
        
        assert isinstance(result, POIExplorationResult)
        assert result.poi_id == 3
        assert result.success is False
        assert result.reward.information == ""
        assert result.reward.gold == 0
        assert result.reward.exp == 0
        assert result.reward.items == []
        assert isinstance(result.timestamp, datetime)
    
    def test_exploration_with_poi_discovery_condition(self, poi_exploration):
        """POI発見条件での探索"""
        condition = POIUnlockCondition(required_poi_discoveries={10, 20})
        reward = POIReward(information="秘密の通路を発見", exp=150)
        poi = POI(
            poi_id=4,
            name="秘密の通路",
            description="隠された通路",
            poi_type=POIType.SECRET_PASSAGE,
            unlock_condition=condition,
            reward=reward
        )
        
        mock_player = Mock()
        
        # 必要なPOIが発見されていない場合
        discovered_pois = {10}  # 20がない
        result = poi_exploration.explore_poi(poi, mock_player, discovered_pois)
        assert result.success is False
        
        # 必要なPOIが発見されている場合
        discovered_pois = {10, 20, 30}
        result = poi_exploration.explore_poi(poi, mock_player, discovered_pois)
        assert result.success is True
        assert result.reward.information == "秘密の通路を発見"
        assert result.reward.exp == 150
    
    def test_exploration_with_complex_conditions(self, poi_exploration):
        """複合条件での探索"""
        condition = POIUnlockCondition(
            required_items={1, 2},
            required_poi_discoveries={100}
        )
        reward = POIReward(
            information="伝説の財宝を発見",
            gold=1000,
            exp=500,
            items=[10, 11, 12]
        )
        poi = POI(
            poi_id=5,
            name="伝説の財宝",
            description="伝説に語り継がれる財宝",
            poi_type=POIType.TREASURE,
            unlock_condition=condition,
            reward=reward
        )
        
        mock_player = Mock()
        
        # アイテム条件のみ満たす
        mock_player.has_item.side_effect = lambda item_id: item_id in {1, 2}
        discovered_pois = set()
        result = poi_exploration.explore_poi(poi, mock_player, discovered_pois)
        assert result.success is False
        
        # POI条件のみ満たす
        mock_player.has_item.side_effect = lambda item_id: False
        discovered_pois = {100}
        result = poi_exploration.explore_poi(poi, mock_player, discovered_pois)
        assert result.success is False
        
        # 両方の条件を満たす
        mock_player.has_item.side_effect = lambda item_id: item_id in {1, 2}
        discovered_pois = {100}
        result = poi_exploration.explore_poi(poi, mock_player, discovered_pois)
        assert result.success is True
        assert result.reward.gold == 1000
        assert result.reward.exp == 500
        assert result.reward.items == [10, 11, 12]
    
    def test_exploration_with_no_conditions(self, poi_exploration):
        """条件なしの探索"""
        condition = POIUnlockCondition()  # 条件なし
        reward = POIReward(information="情報を入手")
        poi = POI(
            poi_id=6,
            name="情報石碑",
            description="誰でも読める石碑",
            poi_type=POIType.INFORMATION,
            unlock_condition=condition,
            reward=reward
        )
        
        mock_player = Mock()
        discovered_pois = set()
        
        result = poi_exploration.explore_poi(poi, mock_player, discovered_pois)
        
        assert result.success is True
        assert result.reward.information == "情報を入手"
    
    def test_exploration_timestamp_different_calls(self, poi_exploration):
        """異なる探索呼び出しでタイムスタンプが異なる"""
        condition = POIUnlockCondition()
        reward = POIReward(information="テスト")
        poi = POI(
            poi_id=7,
            name="テスト",
            description="テスト用",
            poi_type=POIType.INFORMATION,
            unlock_condition=condition,
            reward=reward
        )
        
        mock_player = Mock()
        discovered_pois = set()
        
        result1 = poi_exploration.explore_poi(poi, mock_player, discovered_pois)
        result2 = poi_exploration.explore_poi(poi, mock_player, discovered_pois)
        
        # タイムスタンプは同じか後の時刻である（処理時間によっては同じ場合もある）
        assert result1.timestamp <= result2.timestamp
