import pytest
from src.domain.spot.spot import Spot


class TestSpot:
    """Spotドメインモデルのテストクラス"""

    def test_spot_initialization(self):
        """Spotの初期化テスト"""
        spot = Spot(
            spot_id=1,
            name="テスト場所",
            description="テスト用の場所です"
        )
        
        assert spot.spot_id == 1
        assert spot.name == "テスト場所"
        assert spot.description == "テスト用の場所です"
        assert spot.get_current_player_ids() == set()
        assert spot.get_current_player_count() == 0

    def test_add_player(self):
        """プレイヤー追加のテスト"""
        spot = Spot(
            spot_id=1,
            name="テスト場所",
            description="テスト用の場所です"
        )
        
        # プレイヤーを追加
        spot.add_player(100)
        assert 100 in spot.get_current_player_ids()
        assert spot.get_current_player_count() == 1
        assert spot.is_player_in_spot(100) is True
        
        # 別のプレイヤーを追加
        spot.add_player(200)
        assert 200 in spot.get_current_player_ids()
        assert spot.get_current_player_count() == 2
        assert spot.is_player_in_spot(200) is True

    def test_add_duplicate_player(self):
        """重複するプレイヤー追加のテスト"""
        spot = Spot(
            spot_id=1,
            name="テスト場所",
            description="テスト用の場所です"
        )
        
        # 同じプレイヤーを2回追加
        spot.add_player(100)
        spot.add_player(100)
        
        # setなので重複は無視される
        assert spot.get_current_player_count() == 1
        assert spot.is_player_in_spot(100) is True

    def test_remove_player(self):
        """プレイヤー削除のテスト"""
        spot = Spot(
            spot_id=1,
            name="テスト場所",
            description="テスト用の場所です"
        )
        
        # プレイヤーを追加してから削除
        spot.add_player(100)
        spot.add_player(200)
        assert spot.get_current_player_count() == 2
        
        spot.remove_player(100)
        assert 100 not in spot.get_current_player_ids()
        assert 200 in spot.get_current_player_ids()
        assert spot.get_current_player_count() == 1
        assert spot.is_player_in_spot(100) is False
        assert spot.is_player_in_spot(200) is True

    def test_remove_nonexistent_player(self):
        """存在しないプレイヤーの削除テスト"""
        spot = Spot(
            spot_id=1,
            name="テスト場所",
            description="テスト用の場所です"
        )
        
        # 存在しないプレイヤーを削除（エラーにならない）
        spot.remove_player(999)
        assert spot.get_current_player_count() == 0

    def test_get_current_player_ids(self):
        """現在のプレイヤーID取得のテスト"""
        spot = Spot(
            spot_id=1,
            name="テスト場所",
            description="テスト用の場所です"
        )
        
        spot.add_player(100)
        spot.add_player(200)
        spot.add_player(300)
        
        player_ids = spot.get_current_player_ids()
        assert isinstance(player_ids, set)
        assert player_ids == {100, 200, 300}

    def test_get_current_player_count(self):
        """現在のプレイヤー数取得のテスト"""
        spot = Spot(
            spot_id=1,
            name="テスト場所",
            description="テスト用の場所です"
        )
        
        assert spot.get_current_player_count() == 0
        
        spot.add_player(100)
        assert spot.get_current_player_count() == 1
        
        spot.add_player(200)
        assert spot.get_current_player_count() == 2
        
        spot.remove_player(100)
        assert spot.get_current_player_count() == 1

    def test_is_player_in_spot(self):
        """プレイヤー存在確認のテスト"""
        spot = Spot(
            spot_id=1,
            name="テスト場所",
            description="テスト用の場所です"
        )
        
        # プレイヤーが存在しない場合
        assert spot.is_player_in_spot(100) is False
        
        # プレイヤーを追加後
        spot.add_player(100)
        assert spot.is_player_in_spot(100) is True
        assert spot.is_player_in_spot(200) is False
        
        # プレイヤーを削除後
        spot.remove_player(100)
        assert spot.is_player_in_spot(100) is False

    def test_get_spot_summary(self):
        """スポット概要取得のテスト"""
        spot = Spot(
            spot_id=42,
            name="魔法の森",
            description="神秘的な力が宿る森"
        )
        
        summary = spot.get_spot_summary()
        expected = "魔法の森 (42) 神秘的な力が宿る森"
        assert summary == expected

    def test_spot_with_custom_player_ids(self):
        """カスタムプレイヤーIDセットでの初期化テスト"""
        initial_players = {1, 2, 3}
        spot = Spot(
            spot_id=1,
            name="テスト場所",
            description="テスト用の場所です",
            current_player_ids=initial_players
        )
        
        assert spot.get_current_player_ids() == initial_players
        assert spot.get_current_player_count() == 3
        assert spot.is_player_in_spot(1) is True
        assert spot.is_player_in_spot(2) is True
        assert spot.is_player_in_spot(3) is True
        assert spot.is_player_in_spot(4) is False

    def test_multiple_operations(self):
        """複数操作の組み合わせテスト"""
        spot = Spot(
            spot_id=1,
            name="広場",
            description="町の中央広場"
        )
        
        # 複数のプレイヤーを追加
        players = [101, 102, 103, 104, 105]
        for player_id in players:
            spot.add_player(player_id)
        
        assert spot.get_current_player_count() == 5
        
        # 一部のプレイヤーを削除
        spot.remove_player(102)
        spot.remove_player(104)
        
        assert spot.get_current_player_count() == 3
        assert spot.is_player_in_spot(101) is True
        assert spot.is_player_in_spot(102) is False
        assert spot.is_player_in_spot(103) is True
        assert spot.is_player_in_spot(104) is False
        assert spot.is_player_in_spot(105) is True
        
        # 残っているプレイヤーIDを確認
        remaining_players = spot.get_current_player_ids()
        assert remaining_players == {101, 103, 105}
