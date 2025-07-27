import pytest
from unittest.mock import Mock, patch
from game.action.actions.trade_action import (
    PostTradeStrategy, AcceptTradeStrategy, CancelTradeStrategy,
    GetMyTradesStrategy, GetAvailableTradesStrategy,
    PostTradeCommand, AcceptTradeCommand, CancelTradeCommand,
    GetMyTradesCommand, GetAvailableTradesCommand,
    PostTradeResult, AcceptTradeResult, CancelTradeResult,
    GetMyTradesResult, GetAvailableTradesResult
)
from game.player.player import Player
from game.core.game_context import GameContext
from game.trade.trade_manager import TradeManager
from game.trade.trade_data import TradeOffer
from game.enums import TradeType, TradeStatus


class TestTradeActionStrategies:
    """取引アクション戦略のテスト"""
    
    def setup_method(self):
        self.player = Mock(spec=Player)
        self.player.get_player_id.return_value = "player1"
        self.player.get_name.return_value = "テストプレイヤー"
        
        # statusモックを追加
        self.player.status = Mock()
        self.player.status.get_money.return_value = 1000
        
        self.trade_manager = Mock(spec=TradeManager)
        self.game_context = Mock(spec=GameContext)
        self.game_context.get_trade_manager.return_value = self.trade_manager
    
    def test_post_trade_strategy_arguments(self):
        """取引出品戦略の引数テスト"""
        strategy = PostTradeStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 7
        arg_names = [arg.name for arg in arguments]
        expected_names = [
            "offered_item_id", "offered_item_count", "requested_money",
            "requested_item_id", "requested_item_count", "trade_type",
            "target_player_id"
        ]
        for name in expected_names:
            assert name in arg_names
    
    def test_post_trade_strategy_can_execute(self):
        """取引出品戦略の実行可能性テスト"""
        strategy = PostTradeStrategy()
        
        # TradeManagerが利用可能な場合
        assert strategy.can_execute(self.player, self.game_context) is True
        
        # TradeManagerが利用できない場合
        self.game_context.get_trade_manager.return_value = None
        assert strategy.can_execute(self.player, self.game_context) is False
    
    def test_accept_trade_strategy_arguments(self):
        """取引受託戦略の引数テスト"""
        strategy = AcceptTradeStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 1
        assert arguments[0].name == "trade_id"
    
    def test_cancel_trade_strategy_arguments(self):
        """取引キャンセル戦略の引数テスト"""
        strategy = CancelTradeStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 1
        assert arguments[0].name == "trade_id"
    
    def test_get_my_trades_strategy_arguments(self):
        """自分の取引取得戦略の引数テスト"""
        strategy = GetMyTradesStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 1
        assert arguments[0].name == "include_history"
        assert arguments[0].candidates == ["True", "False"]
    
    def test_get_available_trades_strategy_arguments(self):
        """受託可能取引取得戦略の引数テスト"""
        strategy = GetAvailableTradesStrategy()
        arguments = strategy.get_required_arguments(self.player, self.game_context)
        
        assert len(arguments) == 6
        arg_names = [arg.name for arg in arguments]
        expected_names = [
            "offered_item_id", "requested_item_id", "max_price",
            "min_price", "trade_type", "seller_id"
        ]
        for name in expected_names:
            assert name in arg_names


class TestTradeActionCommands:
    """取引アクションコマンドのテスト"""
    
    def setup_method(self):
        self.player = Mock(spec=Player)
        self.player.get_player_id.return_value = "player1"
        self.player.get_name.return_value = "テストプレイヤー"
        
        # statusモックを追加
        self.player.status = Mock()
        self.player.status.get_money.return_value = 1000
        
        self.trade_manager = Mock(spec=TradeManager)
        self.game_context = Mock(spec=GameContext)
        self.game_context.get_trade_manager.return_value = self.trade_manager
    
    def test_post_trade_command_money_trade(self):
        """お金取引の出品コマンドテスト"""
        # モックの設定
        mock_trade_offer = Mock(spec=TradeOffer)
        mock_trade_offer.trade_id = "trade123"
        mock_trade_offer.get_trade_summary.return_value = "アイテムA x1 ⇄ 100ゴールド"
        
        # プレイヤーのアイテム所持をモック
        self.player.has_item.return_value = True
        self.player.get_inventory_item_count.return_value = 5
        self.player.status.get_money.return_value = 1000
        
        with patch('game.action.actions.trade_action.TradeOffer.create_money_trade', return_value=mock_trade_offer):
            self.trade_manager.post_trade.return_value = True
            
            command = PostTradeCommand("item_a", 1, 100, trade_type="global")
            result = command.execute(self.player, self.game_context)
            
            assert isinstance(result, PostTradeResult)
            assert result.success is True
            assert result.trade_id == "trade123"
            assert result.trade_details == "アイテムA x1 ⇄ 100ゴールド"
    
    def test_post_trade_command_item_trade(self):
        """アイテム取引の出品コマンドテスト"""
        # モックの設定
        mock_trade_offer = Mock(spec=TradeOffer)
        mock_trade_offer.trade_id = "trade456"
        mock_trade_offer.get_trade_summary.return_value = "アイテムA x1 ⇄ アイテムB x2"
        
        # プレイヤーのアイテム所持をモック
        self.player.has_item.return_value = True
        self.player.get_inventory_item_count.return_value = 5
        self.player.status.get_money.return_value = 1000
        
        with patch('game.action.actions.trade_action.TradeOffer.create_item_trade', return_value=mock_trade_offer):
            self.trade_manager.post_trade.return_value = True
            
            command = PostTradeCommand("item_a", 1, 0, "item_b", 2, trade_type="global")
            result = command.execute(self.player, self.game_context)
            
            assert isinstance(result, PostTradeResult)
            assert result.success is True
            assert result.trade_id == "trade456"
            assert result.trade_details == "アイテムA x1 ⇄ アイテムB x2"
    
    def test_post_trade_command_failure(self):
        """取引出品失敗のテスト"""
        # モックの設定
        mock_trade_offer = Mock(spec=TradeOffer)
        mock_trade_offer.trade_id = "trade123"
        mock_trade_offer.get_trade_summary.return_value = "アイテムA x1 ⇄ 100ゴールド"
        
        # プレイヤーのアイテム所持をモック
        self.player.has_item.return_value = True
        self.player.get_inventory_item_count.return_value = 5
        self.player.status.get_money.return_value = 1000
        
        with patch('game.action.actions.trade_action.TradeOffer.create_money_trade', return_value=mock_trade_offer):
            self.trade_manager.post_trade.return_value = False
            
            command = PostTradeCommand("item_a", 1, 100, trade_type="global")
            result = command.execute(self.player, self.game_context)
            
            assert isinstance(result, PostTradeResult)
            assert result.success is False
            assert "取引の出品に失敗しました" in result.message
    
    def test_post_trade_command_no_trade_manager(self):
        """TradeManagerが利用できない場合のテスト"""
        self.game_context.get_trade_manager.return_value = None
        
        command = PostTradeCommand("item_a", 1, 100, trade_type="global")
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, PostTradeResult)
        assert result.success is False
        assert "取引システムが利用できません" in result.message
    
    def test_accept_trade_command_success(self):
        """取引受託成功のテスト"""
        mock_completed_trade = Mock(spec=TradeOffer)
        mock_completed_trade.trade_id = "trade123"
        mock_completed_trade.get_trade_summary.return_value = "アイテムA x1 ⇄ 100ゴールド"
        
        mock_trade = Mock(spec=TradeOffer)
        mock_trade.seller_id = "seller1"
        
        mock_seller = Mock(spec=Player)
        mock_seller.get_player_id.return_value = "seller1"
        
        self.trade_manager.get_trade.return_value = mock_trade
        self.game_context.get_player_manager.return_value.get_player.return_value = mock_seller
        self.trade_manager.accept_trade.return_value = mock_completed_trade
        
        command = AcceptTradeCommand("trade123")
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, AcceptTradeResult)
        assert result.success is True
        assert result.trade_id == "trade123"
        assert result.trade_details == "アイテムA x1 ⇄ 100ゴールド"
    
    def test_accept_trade_command_failure(self):
        """取引受託失敗のテスト"""
        self.trade_manager.accept_trade.side_effect = ValueError("取引が見つかりません")
        
        command = AcceptTradeCommand("invalid_trade_id")
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, AcceptTradeResult)
        assert result.success is False
        assert "取引が見つかりません" in result.message
    
    def test_cancel_trade_command_success(self):
        """取引キャンセル成功のテスト"""
        mock_cancelled_trade = Mock(spec=TradeOffer)
        mock_cancelled_trade.get_trade_summary.return_value = "アイテムA x1 ⇄ 100ゴールド"
        
        self.trade_manager.cancel_trade.return_value = True
        self.trade_manager.get_trade_history.return_value = [mock_cancelled_trade]
        
        command = CancelTradeCommand("trade123")
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, CancelTradeResult)
        assert result.success is True
        assert result.trade_id == "trade123"
        assert result.trade_details == "アイテムA x1 ⇄ 100ゴールド"
    
    def test_cancel_trade_command_failure(self):
        """取引キャンセル失敗のテスト"""
        self.trade_manager.cancel_trade.side_effect = ValueError("取引の出品者のみがキャンセルできます")
        
        command = CancelTradeCommand("trade123")
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, CancelTradeResult)
        assert result.success is False
        assert "取引の出品者のみがキャンセルできます" in result.message
    
    def test_get_my_trades_command_success(self):
        """自分の取引取得成功のテスト"""
        mock_trades = [
            Mock(spec=TradeOffer),
            Mock(spec=TradeOffer)
        ]
        mock_trades[0].get_trade_summary.return_value = "アイテムA x1 ⇄ 100ゴールド"
        mock_trades[1].get_trade_summary.return_value = "アイテムB x2 ⇄ アイテムC x1"
        
        self.trade_manager.get_player_trades.return_value = mock_trades
        
        command = GetMyTradesCommand(include_history=True)
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, GetMyTradesResult)
        assert result.success is True
        assert len(result.trades) == 2
        assert result.include_history is True
    
    def test_get_available_trades_command_success(self):
        """受託可能取引取得成功のテスト"""
        mock_trades = [
            Mock(spec=TradeOffer),
            Mock(spec=TradeOffer)
        ]
        mock_trades[0].get_trade_summary.return_value = "アイテムA x1 ⇄ 100ゴールド"
        mock_trades[1].get_trade_summary.return_value = "アイテムB x2 ⇄ アイテムC x1"
        
        self.trade_manager.get_available_trades_for_player.return_value = mock_trades
        self.trade_manager._matches_filters.return_value = True
        
        filters = {"offered_item_id": "item_a"}
        command = GetAvailableTradesCommand(filters)
        result = command.execute(self.player, self.game_context)
        
        assert isinstance(result, GetAvailableTradesResult)
        assert result.success is True
        assert len(result.trades) == 2
        assert result.filters == filters


class TestTradeActionResultMessages:
    """取引アクション結果メッセージのテスト"""
    
    def test_post_trade_result_success_message(self):
        """取引出品成功メッセージのテスト"""
        result = PostTradeResult(True, "取引を出品しました", "trade123", "アイテムA x1 ⇄ 100ゴールド")
        message = result.to_feedback_message("テストプレイヤー")
        
        assert "テストプレイヤー は取引を出品しました" in message
        assert "取引ID: trade123" in message
        assert "取引詳細: アイテムA x1 ⇄ 100ゴールド" in message
    
    def test_post_trade_result_failure_message(self):
        """取引出品失敗メッセージのテスト"""
        result = PostTradeResult(False, "アイテムが不足しています", None, "")
        message = result.to_feedback_message("テストプレイヤー")
        
        assert "テストプレイヤー は取引を出品できませんでした" in message
        assert "理由: アイテムが不足しています" in message
    
    def test_get_my_trades_result_success_message(self):
        """自分の取引取得成功メッセージのテスト"""
        mock_trades = [
            Mock(spec=TradeOffer),
            Mock(spec=TradeOffer)
        ]
        mock_trades[0].get_trade_summary.return_value = "アイテムA x1 ⇄ 100ゴールド"
        mock_trades[1].get_trade_summary.return_value = "アイテムB x2 ⇄ アイテムC x1"
        
        result = GetMyTradesResult(True, "自分の取引を取得しました", mock_trades, True)
        message = result.to_feedback_message("テストプレイヤー")
        
        assert "テストプレイヤー の取引一覧（履歴含む）" in message
        assert "取引数: 2" in message
        assert "アイテムA x1 ⇄ 100ゴールド" in message
        assert "アイテムB x2 ⇄ アイテムC x1" in message
    
    def test_get_available_trades_result_success_message(self):
        """受託可能取引取得成功メッセージのテスト"""
        mock_trades = [
            Mock(spec=TradeOffer),
            Mock(spec=TradeOffer)
        ]
        mock_trades[0].get_trade_summary.return_value = "アイテムA x1 ⇄ 100ゴールド"
        mock_trades[1].get_trade_summary.return_value = "アイテムB x2 ⇄ アイテムC x1"
        
        filters = {"offered_item_id": "item_a", "max_price": 200}
        result = GetAvailableTradesResult(True, "受託可能な取引を取得しました", mock_trades, filters)
        message = result.to_feedback_message("テストプレイヤー")
        
        assert "テストプレイヤー が受託可能な取引一覧（フィルタ: " in message
        assert "取引数: 2" in message
        assert "アイテムA x1 ⇄ 100ゴールド" in message
        assert "アイテムB x2 ⇄ アイテムC x1" in message


class TestTradeActionIntegration:
    """取引アクション統合テスト"""
    
    def setup_method(self):
        self.trade_manager = TradeManager()
        self.player_manager = Mock()
        self.game_context = GameContext(
            player_manager=self.player_manager,
            spot_manager=Mock(),
            trade_manager=self.trade_manager
        )
        self.player = Mock(spec=Player)
        self.player.get_player_id.return_value = "player1"
        self.player.get_name.return_value = "テストプレイヤー"
        
        # statusモックを追加
        self.player.status = Mock()
        self.player.status.get_money.return_value = 1000
        
        # アイテム所持をモック
        self.player.has_item.return_value = True
        self.player.get_inventory_item_count.return_value = 5
    
    def test_post_and_accept_trade_integration(self):
        """取引出品と受託の統合テスト（アイテム・お金のやり取りなし）"""
        # 取引を出品
        command = PostTradeCommand("item_a", 1, 100, trade_type="global")
        result = command.execute(self.player, self.game_context)
        
        assert result.success is True
        trade_id = result.trade_id
        
        # 取引の存在確認のみ
        trade = self.trade_manager.get_trade(trade_id)
        assert trade is not None
        assert trade.trade_id == trade_id
    
    def test_post_and_cancel_trade_integration(self):
        """取引出品とキャンセルの統合テスト"""
        # 取引を出品
        command = PostTradeCommand("item_a", 1, 100, trade_type="global")
        result = command.execute(self.player, self.game_context)
        
        assert result.success is True
        trade_id = result.trade_id
        
        # 取引をキャンセル
        cancel_command = CancelTradeCommand(trade_id)
        cancel_result = cancel_command.execute(self.player, self.game_context)
        
        assert cancel_result.success is True
        assert cancel_result.trade_id == trade_id
    
    def test_get_my_trades_integration(self):
        """自分の取引取得の統合テスト"""
        # 取引を出品
        command = PostTradeCommand("item_a", 1, 100, trade_type="global")
        result = command.execute(self.player, self.game_context)
        
        assert result.success is True
        
        # 自分の取引を取得
        get_command = GetMyTradesCommand(include_history=False)
        get_result = get_command.execute(self.player, self.game_context)
        
        assert get_result.success is True
        assert len(get_result.trades) == 1
    
    def test_get_available_trades_integration(self):
        """受託可能取引取得の統合テスト"""
        # 他のプレイヤーが取引を出品
        other_player = Mock(spec=Player)
        other_player.get_player_id.return_value = "player2"
        other_player.get_name.return_value = "他のプレイヤー"
        other_player.status = Mock()
        other_player.status.get_money.return_value = 1000
        other_player.has_item.return_value = True
        other_player.get_inventory_item_count.return_value = 5
        
        command = PostTradeCommand("item_a", 1, 100, trade_type="global")
        result = command.execute(other_player, self.game_context)
        
        assert result.success is True
        
        # 受託可能な取引を取得
        get_command = GetAvailableTradesCommand()
        get_result = get_command.execute(self.player, self.game_context)
        
        assert get_result.success is True
        assert len(get_result.trades) == 1 