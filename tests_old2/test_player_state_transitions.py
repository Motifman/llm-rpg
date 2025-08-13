import pytest
from game.player.player import Player
from game.enums import Role, PlayerState
from game.action.action_orchestrator import ActionOrchestrator
from game.core.game_context import GameContext
from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager
from game.world.spot import Spot
from game.conversation.conversation_manager import ConversationManager
from game.sns.sns_manager import SnsManager
from game.trade.trade_manager import TradeManager
from game.battle.battle_manager import BattleManager


@pytest.fixture
def player():
    """テスト用のプレイヤーを作成"""
    return Player("player1", "Test Player", Role.ADVENTURER)


@pytest.fixture
def game_context():
    """テスト用のゲームコンテキストを作成"""
    player_manager = PlayerManager()
    spot_manager = SpotManager()
    conversation_manager = ConversationManager()
    sns_manager = SnsManager()
    trade_manager = TradeManager()
    battle_manager = BattleManager()
    
    # テスト用スポットを作成
    test_spot = Spot("test_spot", "Test Spot", "A test location")
    target_spot = Spot("target_spot", "Target Spot", "A target location")
    
    spot_manager.add_spot(test_spot)
    spot_manager.add_spot(target_spot)
    
    # スポット間の移動を可能にする
    movement_graph = spot_manager.get_movement_graph()
    movement_graph.add_connection("test_spot", "target_spot", "Target Spotへの道")
    
    return GameContext(
        player_manager=player_manager,
        spot_manager=spot_manager,
        conversation_manager=conversation_manager,
        sns_manager=sns_manager,
        trade_manager=trade_manager,
        battle_manager=battle_manager
    )


@pytest.fixture
def orchestrator(game_context):
    """テスト用のActionOrchestratorを作成"""
    return ActionOrchestrator(game_context)


class TestPlayerStateManagement:
    """プレイヤーの状態管理機能のテスト"""
    
    def test_initial_state_is_normal(self, player):
        """初期状態が通常状態であることを確認"""
        assert player.get_player_state() == PlayerState.NORMAL
        assert player.is_in_normal_state() == True
        assert player.is_in_conversation_state() == False
        assert player.is_in_sns_state() == False
        assert player.is_in_battle_state() == False
        assert player.is_in_trading_state() == False
    
    def test_state_transitions(self, player):
        """状態遷移が正常に動作することを確認"""
        # 会話状態に遷移
        player.set_player_state(PlayerState.CONVERSATION)
        assert player.is_in_conversation_state() == True
        assert player.is_in_normal_state() == False
        
        # SNS状態に遷移
        player.set_player_state(PlayerState.SNS)
        assert player.is_in_sns_state() == True
        assert player.is_in_conversation_state() == False
        
        # 戦闘状態に遷移
        player.set_player_state(PlayerState.BATTLE)
        assert player.is_in_battle_state() == True
        assert player.is_in_sns_state() == False
        
        # 取引状態に遷移
        player.set_player_state(PlayerState.TRADING)
        assert player.is_in_trading_state() == True
        assert player.is_in_battle_state() == False
        
        # 通常状態に戻る
        player.set_player_state(PlayerState.NORMAL)
        assert player.is_in_normal_state() == True
        assert player.is_in_trading_state() == False


class TestActionOrchestratorStateFiltering:
    """ActionOrchestratorの状態別行動フィルタリングのテスト"""
    
    def test_normal_state_actions(self, player, game_context, orchestrator):
        """通常状態で利用可能な行動を確認"""
        player.set_current_spot_id("test_spot")
        game_context.get_player_manager().add_player(player)
        
        candidates = orchestrator.get_action_candidates_for_llm(player.get_player_id())
        action_names = [c['action_name'] for c in candidates]
        
        # 通常状態で利用可能な行動が含まれていることを確認
        assert "移動" in action_names
        assert "SNSを開く" in action_names
        assert "取引所を開く" in action_names
        assert "スポット会話開始" in action_names
        
        # 他の状態の行動は含まれていないことを確認
        assert "SNSを閉じる" not in action_names
        assert "会話を離脱する" not in action_names
        assert "戦闘時の行動" not in action_names
    
    def test_conversation_state_actions(self, player, game_context, orchestrator):
        """会話状態で利用可能な行動を確認"""
        player.set_current_spot_id("test_spot")
        player.set_player_state(PlayerState.CONVERSATION)
        game_context.get_player_manager().add_player(player)
        
        candidates = orchestrator.get_action_candidates_for_llm(player.get_player_id())
        action_names = [c['action_name'] for c in candidates]
        
        # 会話状態で利用可能な行動が含まれていることを確認
        assert "会話発言" in action_names
        assert "会話を離脱する" in action_names
        
        # 他の状態の行動は含まれていないことを確認
        assert "SNSを開く" not in action_names
        assert "移動" not in action_names
    
    def test_sns_state_actions(self, player, game_context, orchestrator):
        """SNS状態で利用可能な行動を確認"""
        player.set_current_spot_id("test_spot")
        player.set_player_state(PlayerState.SNS)
        game_context.get_player_manager().add_player(player)
        
        candidates = orchestrator.get_action_candidates_for_llm(player.get_player_id())
        action_names = [c['action_name'] for c in candidates]
        
        # SNS状態で利用可能な行動が含まれていることを確認
        assert "SNS投稿" in action_names
        assert "SNSタイムライン取得" in action_names
        assert "SNSを閉じる" in action_names
        
        # 他の状態の行動は含まれていないことを確認
        assert "移動" not in action_names
        assert "会話発言" not in action_names
    
    def test_battle_state_actions(self, player, game_context, orchestrator):
        """戦闘状態で利用可能な行動を確認"""
        player.set_current_spot_id("test_spot")
        player.set_player_state(PlayerState.BATTLE)
        game_context.get_player_manager().add_player(player)
        
        candidates = orchestrator.get_action_candidates_for_llm(player.get_player_id())
        action_names = [c['action_name'] for c in candidates]
        
        # 戦闘状態では戦闘行動のみが提案される（ただし実際の戦闘に参加していない場合は空）
        # 戦闘状態では他の状態の行動は含まれていないことを確認
        assert "移動" not in action_names
        assert "SNS投稿" not in action_names
        assert "SNSを開く" not in action_names
        
        # 戦闘状態では行動候補が限定されることを確認
        assert len(action_names) <= 1  # 戦闘時の行動のみ、または空
    
    def test_trading_state_actions(self, player, game_context, orchestrator):
        """取引状態で利用可能な行動を確認"""
        player.set_current_spot_id("test_spot")
        player.set_player_state(PlayerState.TRADING)
        game_context.get_player_manager().add_player(player)
        
        candidates = orchestrator.get_action_candidates_for_llm(player.get_player_id())
        action_names = [c['action_name'] for c in candidates]
        
        # 取引状態で利用可能な行動が含まれていることを確認
        assert "取引出品" in action_names
        assert "受託可能取引取得" in action_names
        assert "取引所を閉じる" in action_names
        
        # 他の状態の行動は含まれていないことを確認
        assert "移動" not in action_names
        assert "SNS投稿" not in action_names


class TestStateTransitionActions:
    """状態遷移行動のテスト"""
    
    def test_sns_open_close(self, player, game_context, orchestrator):
        """SNS開く/閉じる行動のテスト"""
        player.set_current_spot_id("test_spot")
        game_context.get_player_manager().add_player(player)
        
        # 通常状態からSNSを開く
        assert player.is_in_normal_state()
        result = orchestrator.execute_llm_action(player.get_player_id(), "SNSを開く", {})
        assert result.success == True
        assert player.is_in_sns_state()
        
        # SNS状態からSNSを閉じる
        result = orchestrator.execute_llm_action(player.get_player_id(), "SNSを閉じる", {})
        assert result.success == True
        assert player.is_in_normal_state()
    
    def test_trading_open_close(self, player, game_context, orchestrator):
        """取引所開く/閉じる行動のテスト"""
        player.set_current_spot_id("test_spot")
        game_context.get_player_manager().add_player(player)
        
        # 通常状態から取引所を開く
        assert player.is_in_normal_state()
        result = orchestrator.execute_llm_action(player.get_player_id(), "取引所を開く", {})
        assert result.success == True
        assert player.is_in_trading_state()
        
        # 取引状態から取引所を閉じる
        result = orchestrator.execute_llm_action(player.get_player_id(), "取引所を閉じる", {})
        assert result.success == True
        assert player.is_in_normal_state()


class TestStateValidation:
    """状態制限の検証テスト"""
    
    def test_cannot_open_sns_from_non_normal_state(self, player, game_context, orchestrator):
        """通常状態以外からSNSを開けないことを確認"""
        player.set_current_spot_id("test_spot")
        game_context.get_player_manager().add_player(player)
        
        # 会話状態からSNSを開こうとする
        player.set_player_state(PlayerState.CONVERSATION)
        result = orchestrator.execute_llm_action(player.get_player_id(), "SNSを開く", {})
        assert result.success == False
    
    def test_cannot_speak_from_non_conversation_state(self, player, game_context, orchestrator):
        """会話状態以外から発言できないことを確認"""
        player.set_current_spot_id("test_spot")
        game_context.get_player_manager().add_player(player)
        
        # 通常状態から会話発言しようとする
        result = orchestrator.execute_llm_action(player.get_player_id(), "会話発言", {"message": "Hello"})
        assert result.success == False
    
    def test_state_specific_action_filtering(self, player, game_context, orchestrator):
        """状態に応じた行動フィルタリングが正常に動作することを確認"""
        player.set_current_spot_id("test_spot")
        game_context.get_player_manager().add_player(player)
        
        # 各状態で利用可能な行動数が異なることを確認
        player.set_player_state(PlayerState.NORMAL)
        normal_candidates = orchestrator.get_action_candidates_for_llm(player.get_player_id())
        
        player.set_player_state(PlayerState.CONVERSATION)
        conversation_candidates = orchestrator.get_action_candidates_for_llm(player.get_player_id())
        
        player.set_player_state(PlayerState.SNS)
        sns_candidates = orchestrator.get_action_candidates_for_llm(player.get_player_id())
        
        # 各状態で異なる数の行動が提案されることを確認
        assert len(normal_candidates) != len(conversation_candidates)
        assert len(conversation_candidates) != len(sns_candidates)
        assert len(sns_candidates) != len(normal_candidates)