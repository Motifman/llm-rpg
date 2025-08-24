import pytest
from datetime import datetime
from src.domain.spot.movement_result import MovementResult


class TestMovementResult:
    """MovementResultのテストクラス"""

    def test_movement_result_initialization(self):
        """MovementResultの初期化テスト"""
        moved_at = datetime.now()
        result = MovementResult(
            player_id=100,
            player_name="テストプレイヤー",
            from_spot_id=10,
            from_spot_name="町",
            to_spot_id=20,
            to_spot_name="森",
            road_id=1,
            road_description="森への道",
            moved_at=moved_at
        )
        
        assert result.player_id == 100
        assert result.player_name == "テストプレイヤー"
        assert result.from_spot_id == 10
        assert result.from_spot_name == "町"
        assert result.to_spot_id == 20
        assert result.to_spot_name == "森"
        assert result.road_id == 1
        assert result.road_description == "森への道"
        assert result.moved_at == moved_at
        assert result.distance == 1.0  # デフォルト値

    def test_movement_result_with_custom_distance(self):
        """カスタム距離でのMovementResult初期化テスト"""
        moved_at = datetime.now()
        result = MovementResult(
            player_id=100,
            player_name="テストプレイヤー",
            from_spot_id=10,
            from_spot_name="町",
            to_spot_id=20,
            to_spot_name="森",
            road_id=1,
            road_description="森への道",
            moved_at=moved_at,
            distance=2.5
        )
        
        assert result.distance == 2.5

    def test_get_move_summary(self):
        """移動概要取得テスト"""
        moved_at = datetime.now()
        result = MovementResult(
            player_id=100,
            player_name="テストプレイヤー",
            from_spot_id=10,
            from_spot_name="町",
            to_spot_id=20,
            to_spot_name="森",
            road_id=1,
            road_description="森への道",
            moved_at=moved_at,
            distance=2.5
        )
        
        summary = result.get_move_summary()
        
        # 概要に必要な情報が含まれていることを確認
        assert "テストプレイヤー" in summary
        assert "町" in summary
        assert "森" in summary
        assert "森への道" in summary
        assert "2.5" in summary  # 距離が含まれていることを確認

    def test_get_move_summary_format(self):
        """移動概要の形式テスト"""
        moved_at = datetime.now()
        result = MovementResult(
            player_id=100,
            player_name="テストプレイヤー",
            from_spot_id=10,
            from_spot_name="町",
            to_spot_id=20,
            to_spot_name="森",
            road_id=1,
            road_description="森への道",
            moved_at=moved_at
        )
        
        summary = result.get_move_summary()
        
        # 概要が文字列であることを確認
        assert isinstance(summary, str)
        assert len(summary) > 0
        
        # 概要に移動に関する情報が含まれていることを確認
        assert "移動" in summary or "move" in summary.lower() or "from" in summary.lower() or "to" in summary.lower()

    def test_movement_result_equality(self):
        """MovementResultの等価性テスト"""
        moved_at = datetime.now()
        result1 = MovementResult(
            player_id=100,
            player_name="テストプレイヤー",
            from_spot_id=10,
            from_spot_name="町",
            to_spot_id=20,
            to_spot_name="森",
            road_id=1,
            road_description="森への道",
            moved_at=moved_at
        )
        
        result2 = MovementResult(
            player_id=100,
            player_name="テストプレイヤー",
            from_spot_id=10,
            from_spot_name="町",
            to_spot_id=20,
            to_spot_name="森",
            road_id=1,
            road_description="森への道",
            moved_at=moved_at
        )
        
        # 同じ内容の結果は等しい
        assert result1 == result2

    def test_movement_result_inequality(self):
        """MovementResultの非等価性テスト"""
        moved_at = datetime.now()
        result1 = MovementResult(
            player_id=100,
            player_name="テストプレイヤー",
            from_spot_id=10,
            from_spot_name="町",
            to_spot_id=20,
            to_spot_name="森",
            road_id=1,
            road_description="森への道",
            moved_at=moved_at
        )
        
        result2 = MovementResult(
            player_id=200,  # 異なるプレイヤーID
            player_name="テストプレイヤー",
            from_spot_id=10,
            from_spot_name="町",
            to_spot_id=20,
            to_spot_name="森",
            road_id=1,
            road_description="森への道",
            moved_at=moved_at
        )
        
        # 異なる内容の結果は等しくない
        assert result1 != result2

    def test_movement_result_representation(self):
        """MovementResultの文字列表現テスト"""
        moved_at = datetime.now()
        result = MovementResult(
            player_id=100,
            player_name="テストプレイヤー",
            from_spot_id=10,
            from_spot_name="町",
            to_spot_id=20,
            to_spot_name="森",
            road_id=1,
            road_description="森への道",
            moved_at=moved_at
        )
        
        # 文字列表現を確認
        result_str = str(result)
        assert "MovementResult" in result_str
        assert "player_id=100" in result_str
        assert "player_name='テストプレイヤー'" in result_str
