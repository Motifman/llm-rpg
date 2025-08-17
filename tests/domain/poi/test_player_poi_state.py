import pytest
from datetime import datetime

from src.domain.poi.player_poi_state import PlayerPOIState
from src.domain.poi.poi_exploration import POIExplorationResult
from src.domain.poi.poi import POIReward


class TestPlayerPOIState:
    """PlayerPOIStateクラスのテスト"""
    
    @pytest.fixture
    def player_poi_state(self):
        """テスト用PlayerPOIState"""
        return PlayerPOIState(player_id="player_123")
    
    @pytest.fixture
    def successful_exploration_result(self):
        """成功した探索結果"""
        reward = POIReward(information="宝箱発見", gold=100, exp=50)
        return POIExplorationResult(
            poi_id="treasure_1",
            success=True,
            reward=reward,
            timestamp=datetime(2023, 1, 1, 12, 0, 0)
        )
    
    @pytest.fixture
    def failed_exploration_result(self):
        """失敗した探索結果"""
        empty_reward = POIReward()
        return POIExplorationResult(
            poi_id="locked_treasure",
            success=False,
            reward=empty_reward,
            timestamp=datetime(2023, 1, 1, 12, 30, 0)
        )
    
    def test_player_poi_state_creation(self, player_poi_state):
        """PlayerPOIStateの作成"""
        assert player_poi_state._player_id == "player_123"
        assert player_poi_state._discovered_pois == {}
        assert player_poi_state._exploration_history == []
    
    def test_record_successful_exploration(self, player_poi_state, successful_exploration_result):
        """成功した探索の記録"""
        spot_id = 100
        
        player_poi_state.record_exploration(spot_id, successful_exploration_result)
        
        # 発見済みPOIに追加される
        assert spot_id in player_poi_state._discovered_pois
        assert "treasure_1" in player_poi_state._discovered_pois[spot_id]
        
        # 探索履歴に追加される
        assert len(player_poi_state._exploration_history) == 1
        assert player_poi_state._exploration_history[0] == successful_exploration_result
    
    def test_record_failed_exploration(self, player_poi_state, failed_exploration_result):
        """失敗した探索の記録"""
        spot_id = 100
        
        player_poi_state.record_exploration(spot_id, failed_exploration_result)
        
        # 発見済みPOIには追加されない
        assert spot_id not in player_poi_state._discovered_pois
        
        # 探索履歴には追加される
        assert len(player_poi_state._exploration_history) == 1
        assert player_poi_state._exploration_history[0] == failed_exploration_result
    
    def test_multiple_poi_discoveries_same_spot(self, player_poi_state):
        """同じスポットで複数のPOI発見"""
        spot_id = 200
        
        # 最初のPOI発見
        result1 = POIExplorationResult(
            poi_id="poi_1",
            success=True,
            reward=POIReward(information="発見1"),
            timestamp=datetime(2023, 1, 1, 10, 0, 0)
        )
        player_poi_state.record_exploration(spot_id, result1)
        
        # 同じスポットで2つ目のPOI発見
        result2 = POIExplorationResult(
            poi_id="poi_2",
            success=True,
            reward=POIReward(information="発見2"),
            timestamp=datetime(2023, 1, 1, 11, 0, 0)
        )
        player_poi_state.record_exploration(spot_id, result2)
        
        # 両方のPOIが記録される
        assert len(player_poi_state._discovered_pois[spot_id]) == 2
        assert "poi_1" in player_poi_state._discovered_pois[spot_id]
        assert "poi_2" in player_poi_state._discovered_pois[spot_id]
        
        # 探索履歴も両方記録される
        assert len(player_poi_state._exploration_history) == 2
    
    def test_multiple_spots_poi_discoveries(self, player_poi_state):
        """異なるスポットでのPOI発見"""
        # スポット100でPOI発見
        result1 = POIExplorationResult(
            poi_id="poi_100_1",
            success=True,
            reward=POIReward(information="スポット100の発見"),
            timestamp=datetime(2023, 1, 1, 10, 0, 0)
        )
        player_poi_state.record_exploration(100, result1)
        
        # スポット200でPOI発見
        result2 = POIExplorationResult(
            poi_id="poi_200_1",
            success=True,
            reward=POIReward(information="スポット200の発見"),
            timestamp=datetime(2023, 1, 1, 11, 0, 0)
        )
        player_poi_state.record_exploration(200, result2)
        
        # 各スポットに対応するPOIが記録される
        assert 100 in player_poi_state._discovered_pois
        assert 200 in player_poi_state._discovered_pois
        assert "poi_100_1" in player_poi_state._discovered_pois[100]
        assert "poi_200_1" in player_poi_state._discovered_pois[200]
        
        # 探索履歴は時系列で記録される
        assert len(player_poi_state._exploration_history) == 2
        assert player_poi_state._exploration_history[0].poi_id == "poi_100_1"
        assert player_poi_state._exploration_history[1].poi_id == "poi_200_1"
    
    def test_mixed_success_and_failure_exploration(self, player_poi_state):
        """成功と失敗が混在する探索記録"""
        spot_id = 300
        
        # 成功した探索
        success_result = POIExplorationResult(
            poi_id="accessible_poi",
            success=True,
            reward=POIReward(information="成功"),
            timestamp=datetime(2023, 1, 1, 10, 0, 0)
        )
        player_poi_state.record_exploration(spot_id, success_result)
        
        # 失敗した探索
        failure_result = POIExplorationResult(
            poi_id="locked_poi",
            success=False,
            reward=POIReward(),
            timestamp=datetime(2023, 1, 1, 10, 30, 0)
        )
        player_poi_state.record_exploration(spot_id, failure_result)
        
        # もう一つ成功した探索
        success_result2 = POIExplorationResult(
            poi_id="another_accessible_poi",
            success=True,
            reward=POIReward(information="再度成功"),
            timestamp=datetime(2023, 1, 1, 11, 0, 0)
        )
        player_poi_state.record_exploration(spot_id, success_result2)
        
        # 成功したもののみが発見済みPOIに記録される
        assert len(player_poi_state._discovered_pois[spot_id]) == 2
        assert "accessible_poi" in player_poi_state._discovered_pois[spot_id]
        assert "another_accessible_poi" in player_poi_state._discovered_pois[spot_id]
        assert "locked_poi" not in player_poi_state._discovered_pois[spot_id]
        
        # 全ての探索が履歴に記録される
        assert len(player_poi_state._exploration_history) == 3
        poi_ids_in_history = [result.poi_id for result in player_poi_state._exploration_history]
        assert "accessible_poi" in poi_ids_in_history
        assert "locked_poi" in poi_ids_in_history
        assert "another_accessible_poi" in poi_ids_in_history
    
    def test_duplicate_poi_discovery_same_spot(self, player_poi_state):
        """同じスポットで同じPOIを重複発見した場合"""
        spot_id = 400
        poi_id = "duplicate_poi"
        
        # 最初の発見
        result1 = POIExplorationResult(
            poi_id=poi_id,
            success=True,
            reward=POIReward(information="最初の発見"),
            timestamp=datetime(2023, 1, 1, 10, 0, 0)
        )
        player_poi_state.record_exploration(spot_id, result1)
        
        # 同じPOIの重複発見
        result2 = POIExplorationResult(
            poi_id=poi_id,
            success=True,
            reward=POIReward(information="重複発見"),
            timestamp=datetime(2023, 1, 1, 11, 0, 0)
        )
        player_poi_state.record_exploration(spot_id, result2)
        
        # 発見済みPOIには重複して追加される（setなので実際は1つだけ）
        assert len(player_poi_state._discovered_pois[spot_id]) == 1
        assert poi_id in player_poi_state._discovered_pois[spot_id]
        
        # 探索履歴には両方記録される
        assert len(player_poi_state._exploration_history) == 2
    
    def test_exploration_history_order(self, player_poi_state):
        """探索履歴の順序確認"""
        timestamps = [
            datetime(2023, 1, 1, 9, 0, 0),
            datetime(2023, 1, 1, 10, 0, 0),
            datetime(2023, 1, 1, 11, 0, 0)
        ]
        
        for i, timestamp in enumerate(timestamps):
            result = POIExplorationResult(
                poi_id=f"poi_{i}",
                success=True,
                reward=POIReward(information=f"発見{i}"),
                timestamp=timestamp
            )
            player_poi_state.record_exploration(100 + i, result)
        
        # 探索履歴は記録順序を保持する
        assert len(player_poi_state._exploration_history) == 3
        for i in range(3):
            assert player_poi_state._exploration_history[i].poi_id == f"poi_{i}"
            assert player_poi_state._exploration_history[i].timestamp == timestamps[i]
