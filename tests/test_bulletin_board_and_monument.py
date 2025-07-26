import pytest
from game.object.interactable import BulletinBoard, Monument
from game.action.actions.interactable_action import (
    WriteBulletinBoardCommand, ReadBulletinBoardCommand, ReadMonumentCommand,
    WriteBulletinBoardResult, ReadBulletinBoardResult, ReadMonumentResult
)
from game.player.player import Player
from game.core.game_context import GameContext
from game.world.spot_manager import SpotManager
from game.world.spot import Spot


class TestBulletinBoard:
    """掲示板のテストクラス"""
    
    def test_bulletin_board_creation(self):
        """掲示板の作成テスト"""
        board = BulletinBoard("board_001", "村の掲示板")
        
        assert board.object_id == "board_001"
        assert board.description == "村の掲示板"
        assert board.display_name == "掲示板"
        assert board.get_post_count() == 0
        assert not board.is_full()
    
    def test_write_post(self):
        """投稿の書き込みテスト"""
        board = BulletinBoard("board_001")
        
        # 正常な投稿
        assert board.write_post("こんにちは")
        assert board.get_post_count() == 1
        assert board.read_posts() == ["こんにちは"]
        
        # 空の投稿は失敗
        assert not board.write_post("")
        assert not board.write_post("   ")
        assert board.get_post_count() == 1
    
    def test_max_posts_limit(self):
        """最大投稿数制限のテスト"""
        board = BulletinBoard("board_001")
        
        # 4つの投稿を追加
        for i in range(4):
            assert board.write_post(f"投稿{i+1}")
        
        assert board.get_post_count() == 4
        assert board.is_full()
        
        # 5つ目の投稿を追加（古い投稿が削除される）
        assert board.write_post("投稿5")
        assert board.get_post_count() == 4
        assert board.is_full()
        
        posts = board.read_posts()
        assert len(posts) == 4
        assert "投稿1" not in posts  # 古い投稿が削除されている
        assert "投稿5" in posts  # 新しい投稿が追加されている
    
    def test_read_posts(self):
        """投稿の読み取りテスト"""
        board = BulletinBoard("board_001")
        
        # 空の掲示板
        assert board.read_posts() == []
        
        # 投稿を追加して読み取り
        board.write_post("投稿1")
        board.write_post("投稿2")
        
        posts = board.read_posts()
        assert len(posts) == 2
        assert "投稿1" in posts
        assert "投稿2" in posts
    
    def test_clear_posts(self):
        """投稿の削除テスト"""
        board = BulletinBoard("board_001")
        
        board.write_post("投稿1")
        board.write_post("投稿2")
        assert board.get_post_count() == 2
        
        board.clear_posts()
        assert board.get_post_count() == 0
        assert board.read_posts() == []


class TestMonument:
    """石碑のテストクラス"""
    
    def test_monument_creation(self):
        """石碑の作成テスト"""
        historical_text = "この地には古代の王国が栄えていた。"
        monument = Monument("monument_001", "古代の石碑", historical_text)
        
        assert monument.object_id == "monument_001"
        assert monument.description == "古代の石碑"
        assert monument.display_name == "石碑"
        assert monument.historical_text == historical_text
    
    def test_read_historical_text(self):
        """石碑の読み取りテスト"""
        historical_text = "伝説によると、この地には勇者が眠っているという。"
        monument = Monument("monument_001", "伝説の石碑", historical_text)
        
        assert monument.read_historical_text() == historical_text
        assert monument.get_historical_text() == historical_text


class TestBulletinBoardActions:
    """掲示板アクションのテストクラス"""
    
    @pytest.fixture
    def game_context(self):
        """テスト用のゲームコンテキストを作成"""
        from game.player.player_manager import PlayerManager
        spot_manager = SpotManager()
        player_manager = PlayerManager()
        game_context = GameContext(player_manager, spot_manager)
        return game_context
    
    @pytest.fixture
    def player(self):
        """テスト用のプレイヤーを作成"""
        from game.enums import Role
        return Player("test_player", "テストプレイヤー", Role.ADVENTURER)
    
    @pytest.fixture
    def spot_with_bulletin_board(self, game_context):
        """掲示板があるスポットを作成"""
        spot = Spot("test_spot", "テストスポット", "テスト用のスポット")
        board = BulletinBoard("board_001", "テスト掲示板")
        spot.add_interactable(board)
        
        spot_manager = game_context.get_spot_manager()
        spot_manager.add_spot(spot)
        
        return spot, board
    
    def test_write_bulletin_board_command_success(self, game_context, player, spot_with_bulletin_board):
        """掲示板への書き込み成功テスト"""
        spot, board = spot_with_bulletin_board
        player.set_current_spot_id("test_spot")
        
        command = WriteBulletinBoardCommand("掲示板", "テスト投稿")
        result = command.execute(player, game_context)
        
        assert result.success
        assert "投稿を書き込みました" in result.message
        assert result.post_content == "テスト投稿"
        assert board.get_post_count() == 1
        assert board.read_posts() == ["テスト投稿"]
    
    def test_write_bulletin_board_command_empty_content(self, game_context, player, spot_with_bulletin_board):
        """空の内容での書き込み失敗テスト"""
        spot, board = spot_with_bulletin_board
        player.set_current_spot_id("test_spot")
        
        command = WriteBulletinBoardCommand("掲示板", "")
        result = command.execute(player, game_context)
        
        assert not result.success
        assert "投稿内容が空です" in result.message
        assert board.get_post_count() == 0
    
    def test_write_bulletin_board_command_no_board(self, game_context, player):
        """掲示板がない場合の失敗テスト"""
        spot = Spot("test_spot", "テストスポット", "テスト用のスポット")
        spot_manager = game_context.get_spot_manager()
        spot_manager.add_spot(spot)
        player.set_current_spot_id("test_spot")
        
        command = WriteBulletinBoardCommand("掲示板", "テスト投稿")
        result = command.execute(player, game_context)
        
        assert not result.success
        assert "この場所に掲示板はありません" in result.message
    
    def test_read_bulletin_board_command_success(self, game_context, player, spot_with_bulletin_board):
        """掲示板の読み取り成功テスト"""
        spot, board = spot_with_bulletin_board
        player.set_current_spot_id("test_spot")
        
        # 投稿を追加
        board.write_post("投稿1")
        board.write_post("投稿2")
        
        command = ReadBulletinBoardCommand("掲示板")
        result = command.execute(player, game_context)
        
        assert result.success
        assert len(result.posts) == 2
        assert "投稿1" in result.posts
        assert "投稿2" in result.posts
    
    def test_read_bulletin_board_command_empty(self, game_context, player, spot_with_bulletin_board):
        """空の掲示板の読み取りテスト"""
        spot, board = spot_with_bulletin_board
        player.set_current_spot_id("test_spot")
        
        command = ReadBulletinBoardCommand("掲示板")
        result = command.execute(player, game_context)
        
        assert result.success
        assert len(result.posts) == 0


class TestMonumentActions:
    """石碑アクションのテストクラス"""
    
    @pytest.fixture
    def game_context(self):
        """テスト用のゲームコンテキストを作成"""
        from game.player.player_manager import PlayerManager
        spot_manager = SpotManager()
        player_manager = PlayerManager()
        game_context = GameContext(player_manager, spot_manager)
        return game_context
    
    @pytest.fixture
    def player(self):
        """テスト用のプレイヤーを作成"""
        from game.enums import Role
        return Player("test_player", "テストプレイヤー", Role.ADVENTURER)
    
    @pytest.fixture
    def spot_with_monument(self, game_context):
        """石碑があるスポットを作成"""
        spot = Spot("test_spot", "テストスポット", "テスト用のスポット")
        historical_text = "この地には古代の王国が栄えていた。"
        monument = Monument("monument_001", "古代の石碑", historical_text)
        spot.add_interactable(monument)
        
        spot_manager = game_context.get_spot_manager()
        spot_manager.add_spot(spot)
        
        return spot, monument
    
    def test_read_monument_command_success(self, game_context, player, spot_with_monument):
        """石碑の読み取り成功テスト"""
        spot, monument = spot_with_monument
        player.set_current_spot_id("test_spot")
        
        command = ReadMonumentCommand("石碑")
        result = command.execute(player, game_context)
        
        assert result.success
        assert result.historical_text == "この地には古代の王国が栄えていた。"
        assert "石碑" in result.message
    
    def test_read_monument_command_no_monument(self, game_context, player):
        """石碑がない場合の失敗テスト"""
        spot = Spot("test_spot", "テストスポット", "テスト用のスポット")
        spot_manager = game_context.get_spot_manager()
        spot_manager.add_spot(spot)
        player.set_current_spot_id("test_spot")
        
        command = ReadMonumentCommand("石碑")
        result = command.execute(player, game_context)
        
        assert not result.success
        assert "この場所に石碑はありません" in result.message


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 