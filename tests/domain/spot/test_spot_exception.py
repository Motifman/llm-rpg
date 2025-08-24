import pytest
from src.domain.spot.spot_exception import (
    SpotException,
    PlayerNotMeetConditionException,
    PlayerAlreadyInSpotException,
    PlayerNotInSpotException,
    SpotNotConnectedException,
    RoadNotConnectedToFromSpotException,
    RoadNotConnectedToToSpotException
)


class TestSpotException:
    """SpotExceptionのテストクラス"""

    def test_spot_exception_inheritance(self):
        """SpotExceptionの継承関係テスト"""
        exception = SpotException("テストエラー")
        assert isinstance(exception, Exception)
        assert str(exception) == "テストエラー"

    def test_spot_exception_without_message(self):
        """メッセージなしのSpotExceptionテスト"""
        exception = SpotException()
        assert isinstance(exception, Exception)


class TestPlayerNotMeetConditionException:
    """PlayerNotMeetConditionExceptionのテストクラス"""

    def test_player_not_meet_condition_exception_inheritance(self):
        """PlayerNotMeetConditionExceptionの継承関係テスト"""
        exception = PlayerNotMeetConditionException("条件を満たしていません")
        assert isinstance(exception, SpotException)
        assert isinstance(exception, Exception)
        assert str(exception) == "条件を満たしていません"

    def test_player_not_meet_condition_exception_without_message(self):
        """メッセージなしのPlayerNotMeetConditionExceptionテスト"""
        exception = PlayerNotMeetConditionException()
        assert isinstance(exception, SpotException)


class TestPlayerAlreadyInSpotException:
    """PlayerAlreadyInSpotExceptionのテストクラス"""

    def test_player_already_in_spot_exception_inheritance(self):
        """PlayerAlreadyInSpotExceptionの継承関係テスト"""
        exception = PlayerAlreadyInSpotException("プレイヤーは既にスポットにいます")
        assert isinstance(exception, SpotException)
        assert isinstance(exception, Exception)
        assert str(exception) == "プレイヤーは既にスポットにいます"

    def test_player_already_in_spot_exception_without_message(self):
        """メッセージなしのPlayerAlreadyInSpotExceptionテスト"""
        exception = PlayerAlreadyInSpotException()
        assert isinstance(exception, SpotException)


class TestPlayerNotInSpotException:
    """PlayerNotInSpotExceptionのテストクラス"""

    def test_player_not_in_spot_exception_inheritance(self):
        """PlayerNotInSpotExceptionの継承関係テスト"""
        exception = PlayerNotInSpotException("プレイヤーはスポットにいません")
        assert isinstance(exception, SpotException)
        assert isinstance(exception, Exception)
        assert str(exception) == "プレイヤーはスポットにいません"

    def test_player_not_in_spot_exception_without_message(self):
        """メッセージなしのPlayerNotInSpotExceptionテスト"""
        exception = PlayerNotInSpotException()
        assert isinstance(exception, SpotException)


class TestSpotNotConnectedException:
    """SpotNotConnectedExceptionのテストクラス"""

    def test_spot_not_connected_exception_inheritance(self):
        """SpotNotConnectedExceptionの継承関係テスト"""
        exception = SpotNotConnectedException("スポットが接続されていません")
        assert isinstance(exception, SpotException)
        assert isinstance(exception, Exception)
        assert str(exception) == "スポットが接続されていません"

    def test_spot_not_connected_exception_without_message(self):
        """メッセージなしのSpotNotConnectedExceptionテスト"""
        exception = SpotNotConnectedException()
        assert isinstance(exception, SpotException)


class TestRoadNotConnectedToFromSpotException:
    """RoadNotConnectedToFromSpotExceptionのテストクラス"""

    def test_road_not_connected_to_from_spot_exception_inheritance(self):
        """RoadNotConnectedToFromSpotExceptionの継承関係テスト"""
        exception = RoadNotConnectedToFromSpotException("道路が開始スポットに接続されていません")
        assert isinstance(exception, SpotException)
        assert isinstance(exception, Exception)
        assert str(exception) == "道路が開始スポットに接続されていません"

    def test_road_not_connected_to_from_spot_exception_without_message(self):
        """メッセージなしのRoadNotConnectedToFromSpotExceptionテスト"""
        exception = RoadNotConnectedToFromSpotException()
        assert isinstance(exception, SpotException)


class TestRoadNotConnectedToToSpotException:
    """RoadNotConnectedToToSpotExceptionのテストクラス"""

    def test_road_not_connected_to_to_spot_exception_inheritance(self):
        """RoadNotConnectedToToSpotExceptionの継承関係テスト"""
        exception = RoadNotConnectedToToSpotException("道路が終了スポットに接続されていません")
        assert isinstance(exception, SpotException)
        assert isinstance(exception, Exception)
        assert str(exception) == "道路が終了スポットに接続されていません"

    def test_road_not_connected_to_to_spot_exception_without_message(self):
        """メッセージなしのRoadNotConnectedToToSpotExceptionテスト"""
        exception = RoadNotConnectedToToSpotException()
        assert isinstance(exception, SpotException)


class TestSpotExceptionHierarchy:
    """SpotException階層のテストクラス"""

    def test_exception_hierarchy(self):
        """例外階層の確認テスト"""
        # 基底例外
        base_exception = SpotException("基底例外")
        assert isinstance(base_exception, Exception)
        
        # 各具体的な例外
        condition_exception = PlayerNotMeetConditionException("条件例外")
        already_in_exception = PlayerAlreadyInSpotException("既在例外")
        not_in_exception = PlayerNotInSpotException("不在例外")
        not_connected_exception = SpotNotConnectedException("未接続例外")
        road_from_exception = RoadNotConnectedToFromSpotException("道路開始例外")
        road_to_exception = RoadNotConnectedToToSpotException("道路終了例外")
        
        # すべてがSpotExceptionのサブクラスであることを確認
        assert isinstance(condition_exception, SpotException)
        assert isinstance(already_in_exception, SpotException)
        assert isinstance(not_in_exception, SpotException)
        assert isinstance(not_connected_exception, SpotException)
        assert isinstance(road_from_exception, SpotException)
        assert isinstance(road_to_exception, SpotException)
        
        # すべてがExceptionのサブクラスであることを確認
        assert isinstance(condition_exception, Exception)
        assert isinstance(already_in_exception, Exception)
        assert isinstance(not_in_exception, Exception)
        assert isinstance(not_connected_exception, Exception)
        assert isinstance(road_from_exception, Exception)
        assert isinstance(road_to_exception, Exception)

    def test_exception_uniqueness(self):
        """例外の一意性テスト"""
        # 異なる例外クラスは異なるインスタンスであることを確認
        condition_exception = PlayerNotMeetConditionException("条件例外")
        already_in_exception = PlayerAlreadyInSpotException("既在例外")
        
        assert type(condition_exception) != type(already_in_exception)
        assert not isinstance(condition_exception, PlayerAlreadyInSpotException)
        assert not isinstance(already_in_exception, PlayerNotMeetConditionException)
