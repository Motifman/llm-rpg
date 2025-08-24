import pytest
from datetime import datetime
from src.domain.spot.movement_service import MovementService
from src.domain.spot.spot import Spot
from src.domain.spot.road import Road
from src.domain.spot.condition import LevelConditionChecker
from src.domain.player.level import Level
from src.domain.spot.spot_exception import PlayerNotMeetConditionException


class TestMovementService:
    """MovementServiceドメインサービスのテストクラス"""

    def test_movement_service_initialization(self):
        """MovementServiceの初期化テスト"""
        service = MovementService()
        assert service is not None

    def test_move_player_to_spot_success(self):
        """プレイヤー移動成功テスト"""
        service = MovementService()
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, name, current_spot_id):
                self.player_id = player_id
                self.name = name
                self.current_spot_id = current_spot_id
            
            def move_to_spot(self, spot_id):
                self.current_spot_id = spot_id
        
        # スポットと道路を作成
        from_spot = Spot(spot_id=10, name="町", description="小さな町")
        to_spot = Spot(spot_id=20, name="森", description="神秘的な森")
        road = Road(road_id=1, from_spot_id=10, to_spot_id=20, description="森への道")
        
        # プレイヤーを作成
        player = MockPlayer(player_id=100, name="テストプレイヤー", current_spot_id=10)
        
        # プレイヤーを開始スポットに追加
        from_spot.add_player(player.player_id)
        
        # 移動実行
        result = service.move_player_to_spot(player, from_spot, to_spot, road)
        
        # 結果を検証
        assert result.player_id == 100
        assert result.player_name == "テストプレイヤー"
        assert result.from_spot_id == 10
        assert result.from_spot_name == "町"
        assert result.to_spot_id == 20
        assert result.to_spot_name == "森"
        assert result.road_id == 1
        assert result.road_description == "森への道"
        assert isinstance(result.moved_at, datetime)
        assert result.distance == 1.0  # デフォルト距離
        
        # プレイヤーの位置が更新されていることを確認
        assert player.current_spot_id == 20
        
        # スポットのプレイヤーリストが更新されていることを確認
        assert from_spot.get_current_player_count() == 0
        assert to_spot.get_current_player_count() == 1
        assert to_spot.is_player_in_spot(100) is True

    def test_move_player_to_spot_with_conditions_success(self):
        """条件付き道路でのプレイヤー移動成功テスト"""
        service = MovementService()
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, name, current_spot_id, level):
                self.player_id = player_id
                self.name = name
                self.current_spot_id = current_spot_id
                self._level = level
            
            def move_to_spot(self, spot_id):
                self.current_spot_id = spot_id
            
            def level_is_above(self, required_level):
                return self._level >= required_level.value
        
        # スポットと条件付き道路を作成
        from_spot = Spot(spot_id=10, name="町", description="小さな町")
        to_spot = Spot(spot_id=20, name="森", description="神秘的な森")
        level_condition = LevelConditionChecker(5)
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道",
            conditions=level_condition
        )
        
        # 条件を満たすプレイヤーを作成
        player = MockPlayer(player_id=100, name="テストプレイヤー", current_spot_id=10, level=7)
        
        # プレイヤーを開始スポットに追加
        from_spot.add_player(player.player_id)
        
        # 移動実行
        result = service.move_player_to_spot(player, from_spot, to_spot, road)
        
        # 結果を検証
        assert result.player_id == 100
        assert result.player_name == "テストプレイヤー"
        assert result.from_spot_id == 10
        assert result.to_spot_id == 20
        assert result.road_id == 1

    def test_move_player_to_spot_with_conditions_failure(self):
        """条件付き道路でのプレイヤー移動失敗テスト"""
        service = MovementService()
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, name, current_spot_id, level):
                self.player_id = player_id
                self.name = name
                self.current_spot_id = current_spot_id
                self._level = level
            
            def move_to_spot(self, spot_id):
                self.current_spot_id = spot_id
            
            def level_is_above(self, required_level):
                return self._level >= required_level.value
        
        # スポットと条件付き道路を作成
        from_spot = Spot(spot_id=10, name="町", description="小さな町")
        to_spot = Spot(spot_id=20, name="森", description="神秘的な森")
        level_condition = LevelConditionChecker(5)
        road = Road(
            road_id=1,
            from_spot_id=10,
            to_spot_id=20,
            description="森への道",
            conditions=level_condition
        )
        
        # 条件を満たさないプレイヤーを作成
        player = MockPlayer(player_id=100, name="テストプレイヤー", current_spot_id=10, level=3)
        
        # 移動実行で例外が発生することを確認
        with pytest.raises(PlayerNotMeetConditionException) as exc_info:
            service.move_player_to_spot(player, from_spot, to_spot, road)
        
        assert "Player 100 does not meet the level condition: 5" in str(exc_info.value)
        
        # プレイヤーの位置が変更されていないことを確認
        assert player.current_spot_id == 10

    def test_move_player_to_spot_with_existing_players(self):
        """既存プレイヤーがいるスポットへの移動テスト"""
        service = MovementService()
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, name, current_spot_id):
                self.player_id = player_id
                self.name = name
                self.current_spot_id = current_spot_id
            
            def move_to_spot(self, spot_id):
                self.current_spot_id = spot_id
        
        # スポットと道路を作成（既存プレイヤーあり）
        from_spot = Spot(spot_id=10, name="町", description="小さな町")
        to_spot = Spot(
            spot_id=20,
            name="森",
            description="神秘的な森",
            current_player_ids={200, 300}  # 既存プレイヤー
        )
        road = Road(road_id=1, from_spot_id=10, to_spot_id=20, description="森への道")
        
        # プレイヤーを作成
        player = MockPlayer(player_id=100, name="テストプレイヤー", current_spot_id=10)
        
        # プレイヤーを開始スポットに追加
        from_spot.add_player(player.player_id)
        
        # 移動実行
        result = service.move_player_to_spot(player, from_spot, to_spot, road)
        
        # 結果を検証
        assert result.player_id == 100
        assert result.to_spot_id == 20
        
        # 既存プレイヤーと新しいプレイヤーがいることを確認
        assert to_spot.get_current_player_count() == 3
        assert to_spot.is_player_in_spot(100) is True
        assert to_spot.is_player_in_spot(200) is True
        assert to_spot.is_player_in_spot(300) is True

    def test_move_player_to_spot_domain_events(self):
        """プレイヤー移動時のドメインイベントテスト"""
        service = MovementService()
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, name, current_spot_id):
                self.player_id = player_id
                self.name = name
                self.current_spot_id = current_spot_id
            
            def move_to_spot(self, spot_id):
                self.current_spot_id = spot_id
        
        # スポットと道路を作成
        from_spot = Spot(spot_id=10, name="町", description="小さな町")
        to_spot = Spot(spot_id=20, name="森", description="神秘的な森")
        road = Road(road_id=1, from_spot_id=10, to_spot_id=20, description="森への道")
        
        # プレイヤーを作成
        player = MockPlayer(player_id=100, name="テストプレイヤー", current_spot_id=10)
        
        # プレイヤーを開始スポットに追加
        from_spot.add_player(player.player_id)
        
        # 移動実行
        result = service.move_player_to_spot(player, from_spot, to_spot, road)
        
        # ドメインイベントが発生していることを確認
        from_events = from_spot.get_events()
        to_events = to_spot.get_events()
        
        assert len(from_events) == 2  # 追加時と削除時のイベント
        assert from_events[1].__class__.__name__ == "PlayerExitedSpotEvent"
        assert from_events[1].player_id == 100
        assert from_events[1].spot_id == 10
        
        assert len(to_events) == 1
        assert to_events[0].__class__.__name__ == "PlayerEnteredSpotEvent"
        assert to_events[0].player_id == 100
        assert to_events[0].spot_id == 20

    def test_move_result_get_move_summary(self):
        """移動結果の概要取得テスト"""
        service = MovementService()
        
        # モックプレイヤーを作成
        class MockPlayer:
            def __init__(self, player_id, name, current_spot_id):
                self.player_id = player_id
                self.name = name
                self.current_spot_id = current_spot_id
            
            def move_to_spot(self, spot_id):
                self.current_spot_id = spot_id
        
        # スポットと道路を作成
        from_spot = Spot(spot_id=10, name="町", description="小さな町")
        to_spot = Spot(spot_id=20, name="森", description="神秘的な森")
        road = Road(road_id=1, from_spot_id=10, to_spot_id=20, description="森への道")
        
        # プレイヤーを作成
        player = MockPlayer(player_id=100, name="テストプレイヤー", current_spot_id=10)
        
        # プレイヤーを開始スポットに追加
        from_spot.add_player(player.player_id)
        
        # 移動実行
        result = service.move_player_to_spot(player, from_spot, to_spot, road)
        
        # 移動概要を取得
        summary = result.get_move_summary()
        
        # 概要に必要な情報が含まれていることを確認
        assert "テストプレイヤー" in summary
        assert "町" in summary
        assert "森" in summary
        assert "森への道" in summary
