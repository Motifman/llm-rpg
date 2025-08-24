import pytest
from src.domain.spot.spot_events import PlayerEnteredSpotEvent, PlayerExitedSpotEvent


class TestPlayerEnteredSpotEvent:
    """PlayerEnteredSpotEventのテストクラス"""

    def test_player_entered_spot_event_creation(self):
        """PlayerEnteredSpotEventの作成テスト"""
        event = PlayerEnteredSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        assert event.aggregate_id == 1
        assert event.aggregate_type == "spot"
        assert event.player_id == 100
        assert event.spot_id == 10

    def test_player_entered_spot_event_immutability(self):
        """PlayerEnteredSpotEventの不変性テスト"""
        event = PlayerEnteredSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        # frozen=Trueなので属性の変更はできない
        with pytest.raises(Exception):
            event.player_id = 200

    def test_player_entered_spot_event_representation(self):
        """PlayerEnteredSpotEventの文字列表現テスト"""
        event = PlayerEnteredSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        # イベントの文字列表現を確認
        event_str = str(event)
        assert "PlayerEnteredSpotEvent" in event_str
        assert "player_id=100" in event_str
        assert "spot_id=10" in event_str


class TestPlayerExitedSpotEvent:
    """PlayerExitedSpotEventのテストクラス"""

    def test_player_exited_spot_event_creation(self):
        """PlayerExitedSpotEventの作成テスト"""
        event = PlayerExitedSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        assert event.aggregate_id == 1
        assert event.aggregate_type == "spot"
        assert event.player_id == 100
        assert event.spot_id == 10

    def test_player_exited_spot_event_immutability(self):
        """PlayerExitedSpotEventの不変性テスト"""
        event = PlayerExitedSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        # frozen=Trueなので属性の変更はできない
        with pytest.raises(Exception):
            event.player_id = 200

    def test_player_exited_spot_event_representation(self):
        """PlayerExitedSpotEventの文字列表現テスト"""
        event = PlayerExitedSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        # イベントの文字列表現を確認
        event_str = str(event)
        assert "PlayerExitedSpotEvent" in event_str
        assert "player_id=100" in event_str
        assert "spot_id=10" in event_str


class TestSpotEventsComparison:
    """SpotEventsの比較テストクラス"""

    def test_events_equality(self):
        """同じ内容のイベントの等価性テスト（event_idとoccurred_atを除く）"""
        event1 = PlayerEnteredSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        event2 = PlayerEnteredSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        # event_idとoccurred_atを除いて比較
        assert event1.aggregate_id == event2.aggregate_id
        assert event1.aggregate_type == event2.aggregate_type
        assert event1.player_id == event2.player_id
        assert event1.spot_id == event2.spot_id

    def test_events_inequality(self):
        """異なる内容のイベントの非等価性テスト"""
        event1 = PlayerEnteredSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        event2 = PlayerEnteredSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=200,  # 異なるプレイヤーID
            spot_id=10
        )
        
        assert event1.player_id != event2.player_id

    def test_different_event_types_inequality(self):
        """異なるタイプのイベントの非等価性テスト"""
        entered_event = PlayerEnteredSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        exited_event = PlayerExitedSpotEvent.create(
            aggregate_id=1,
            aggregate_type="spot",
            player_id=100,
            spot_id=10
        )
        
        assert type(entered_event) != type(exited_event)
