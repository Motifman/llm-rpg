import pytest
from game.action.actions.conversation_action import (
    StartSpotConversationCommand,
    StartPrivateConversationCommand,
    JoinSpotConversationCommand,
    SpeakInConversationCommand,
    LeaveConversationCommand,
    StartConversationResult,
    JoinConversationResult,
    SpeakResult,
    LeaveConversationResult
)
from game.conversation.conversation_manager import ConversationManager
from game.conversation.message_data import LocationChatMessage
from game.player.player import Player
from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager
from game.core.game_context import GameContext
from game.enums import Role


class TestConversationAction:
    """会話アクションのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        # プレイヤーマネージャーを作成
        self.player_manager = PlayerManager()
        self.player1 = Player("player_001", "プレイヤー1", Role.ADVENTURER)
        self.player2 = Player("player_002", "プレイヤー2", Role.MERCHANT)
        self.player3 = Player("player_003", "プレイヤー3", Role.CRAFTSMAN)
        
        # プレイヤーをスポットに配置
        self.player1.set_current_spot_id("tavern_01")
        self.player2.set_current_spot_id("tavern_01")
        self.player3.set_current_spot_id("shop_01")
        
        self.player_manager.add_player(self.player1)
        self.player_manager.add_player(self.player2)
        self.player_manager.add_player(self.player3)
        
        # スポットマネージャーを作成
        self.spot_manager = SpotManager()
        
        # 会話マネージャーを作成
        self.conversation_manager = ConversationManager()
        
        # ゲームコンテキストを作成
        self.game_context = GameContext(
            player_manager=self.player_manager,
            spot_manager=self.spot_manager,
            conversation_manager=self.conversation_manager
        )
    
    def test_start_spot_conversation_success(self):
        """スポット会話開始の成功テスト"""
        command = StartSpotConversationCommand("tavern_01")
        result = command.execute(self.player1, self.game_context)
        
        assert isinstance(result, StartConversationResult)
        assert result.success is True
        assert result.session_id is not None
        assert "tavern_01" in result.message
        assert result.participants is not None
        assert result.history is not None
        
        # セッションが作成されていることを確認
        session = self.conversation_manager.sessions.get(result.session_id)
        assert session is not None
        assert session.spot_id == "tavern_01"
        assert self.player1.get_player_id() in session.participants
    
    def test_start_spot_conversation_already_in_conversation(self):
        """既に会話に参加している場合のテスト"""
        # 最初の会話を開始
        command1 = StartSpotConversationCommand("tavern_01")
        result1 = command1.execute(self.player1, self.game_context)
        assert result1.success is True
        
        # 同じプレイヤーが別の会話を開始しようとする
        command2 = StartSpotConversationCommand("shop_01")
        result2 = command2.execute(self.player1, self.game_context)
        
        assert isinstance(result2, StartConversationResult)
        assert result2.success is False
        assert "既に他の会話に参加しています" in result2.message
        assert result2.participants == []
        assert result2.history == ""
    
    def test_start_private_conversation_success(self):
        """個人会話開始の成功テスト"""
        command = StartPrivateConversationCommand("player_002", "tavern_01")
        result = command.execute(self.player1, self.game_context)
        
        assert isinstance(result, StartConversationResult)
        assert result.success is True
        assert result.session_id is not None
        assert "player_002" in result.message
        assert result.participants is not None
        assert result.history is not None
        
        # 個人宛セッションが作成されていることを確認
        session = self.conversation_manager.sessions.get(result.session_id)
        assert session is not None
        assert session.is_private is True
        assert self.player1.get_player_id() in session.participants
    
    def test_join_spot_conversation_success(self):
        """スポット会話参加の成功テスト"""
        # プレイヤー1が会話を開始
        start_command = StartSpotConversationCommand("tavern_01")
        start_result = start_command.execute(self.player1, self.game_context)
        assert start_result.success is True
        
        # プレイヤー2が会話に参加
        join_command = JoinSpotConversationCommand("tavern_01")
        join_result = join_command.execute(self.player2, self.game_context)
        
        assert isinstance(join_result, JoinConversationResult)
        assert join_result.success is True
        assert join_result.session_id == start_result.session_id
        assert join_result.participants is not None
        assert join_result.history is not None
        
        # 両方のプレイヤーが参加者リストに含まれていることを確認
        session = self.conversation_manager.sessions.get(join_result.session_id)
        assert self.player1.get_player_id() in session.participants
        assert self.player2.get_player_id() in session.participants
    
    def test_join_spot_conversation_no_active_session(self):
        """アクティブなセッションがない場合のテスト"""
        command = JoinSpotConversationCommand("tavern_01")
        result = command.execute(self.player1, self.game_context)
        
        assert isinstance(result, JoinConversationResult)
        assert result.success is False
        assert "アクティブな会話セッションがありません" in result.message
        assert result.participants == []
        assert result.history == ""
    
    def test_join_spot_conversation_already_in_conversation(self):
        """既に会話に参加している場合のテスト"""
        # プレイヤー1が会話を開始
        start_command = StartSpotConversationCommand("tavern_01")
        start_result = start_command.execute(self.player1, self.game_context)
        assert start_result.success is True
        
        # プレイヤー2が別の会話を開始
        start_command2 = StartSpotConversationCommand("shop_01")
        start_result2 = start_command2.execute(self.player2, self.game_context)
        assert start_result2.success is True
        
        # プレイヤー2が別の会話に参加しようとする
        join_command = JoinSpotConversationCommand("tavern_01")
        join_result = join_command.execute(self.player2, self.game_context)
        
        assert isinstance(join_result, JoinConversationResult)
        assert join_result.success is False
        assert "既に他の会話に参加しています" in join_result.message
        assert join_result.participants == []
        assert join_result.history == ""
    
    def test_speak_in_conversation_success(self):
        """会話発言の成功テスト"""
        # プレイヤー1が会話を開始
        start_command = StartSpotConversationCommand("tavern_01")
        start_result = start_command.execute(self.player1, self.game_context)
        assert start_result.success is True
        
        # プレイヤー1が発言
        speak_command = SpeakInConversationCommand("こんにちは！")
        speak_result = speak_command.execute(self.player1, self.game_context)
        
        assert isinstance(speak_result, SpeakResult)
        assert speak_result.success is True
        assert speak_result.session_id == start_result.session_id
        assert speak_result.participants is not None
        assert speak_result.history is not None
        
        # メッセージが記録されていることを確認
        session = self.conversation_manager.sessions.get(speak_result.session_id)
        history = session.get_conversation_history()
        assert len(history) >= 2  # 開始メッセージ + 発言メッセージ
        
        # 最新のメッセージが発言内容と一致することを確認
        latest_message = history[-1]
        assert latest_message.content == "こんにちは！"
        assert latest_message.sender_id == self.player1.get_player_id()
    
    def test_speak_in_conversation_not_in_conversation(self):
        """会話に参加していない場合のテスト"""
        command = SpeakInConversationCommand("こんにちは！")
        result = command.execute(self.player1, self.game_context)
        
        assert isinstance(result, SpeakResult)
        assert result.success is False
        assert "会話に参加していません" in result.message
        assert result.participants == []
        assert result.history == ""
    
    def test_speak_in_conversation_targeted_message(self):
        """特定プレイヤーへの発言テスト"""
        # プレイヤー1が会話を開始
        start_command = StartSpotConversationCommand("tavern_01")
        start_result = start_command.execute(self.player1, self.game_context)
        assert start_result.success is True
        
        # プレイヤー2が会話に参加
        join_command = JoinSpotConversationCommand("tavern_01")
        join_result = join_command.execute(self.player2, self.game_context)
        assert join_result.success is True
        
        # プレイヤー1がプレイヤー2に話しかける
        speak_command = SpeakInConversationCommand("こんにちは！", "player_002")
        speak_result = speak_command.execute(self.player1, self.game_context)
        
        assert isinstance(speak_result, SpeakResult)
        assert speak_result.success is True
        assert speak_result.participants is not None
        assert speak_result.history is not None
        
        # メッセージが記録されていることを確認
        session = self.conversation_manager.sessions.get(speak_result.session_id)
        history = session.get_conversation_history()
        latest_message = history[-1]
        assert latest_message.content == "こんにちは！"
        assert latest_message.target_player_id == "player_002"
    
    def test_leave_conversation_success(self):
        """会話離脱の成功テスト"""
        # プレイヤー1が会話を開始
        start_command = StartSpotConversationCommand("tavern_01")
        start_result = start_command.execute(self.player1, self.game_context)
        assert start_result.success is True
        
        # プレイヤー2が会話に参加
        join_command = JoinSpotConversationCommand("tavern_01")
        join_result = join_command.execute(self.player2, self.game_context)
        assert join_result.success is True
        
        # プレイヤー1が離脱
        leave_command = LeaveConversationCommand()
        leave_result = leave_command.execute(self.player1, self.game_context)
        
        assert isinstance(leave_result, LeaveConversationResult)
        assert leave_result.success is True
        assert leave_result.participants is not None
        assert leave_result.history is not None
        
        # プレイヤー1が参加者リストから削除されていることを確認
        session = self.conversation_manager.sessions.get(leave_result.session_id)
        assert self.player1.get_player_id() not in session.participants
        assert self.player2.get_player_id() in session.participants  # プレイヤー2は残っている
    
    def test_leave_conversation_not_in_conversation(self):
        """会話に参加していない場合のテスト"""
        command = LeaveConversationCommand()
        result = command.execute(self.player1, self.game_context)
        
        assert isinstance(result, LeaveConversationResult)
        assert result.success is False
        assert "会話に参加していません" in result.message
        assert result.participants == []
        assert result.history == ""
    
    def test_leave_conversation_session_end(self):
        """最後の参加者が離脱した場合のセッション終了テスト"""
        # プレイヤー1が会話を開始
        start_command = StartSpotConversationCommand("tavern_01")
        start_result = start_command.execute(self.player1, self.game_context)
        assert start_result.success is True
        
        # プレイヤー1が離脱（唯一の参加者）
        leave_command = LeaveConversationCommand()
        leave_result = leave_command.execute(self.player1, self.game_context)
        
        assert isinstance(leave_result, LeaveConversationResult)
        assert leave_result.success is True
        assert leave_result.participants is not None
        assert leave_result.history is not None
        
        # セッションが終了していることを確認
        session = self.conversation_manager.sessions.get(leave_result.session_id)
        assert session is None or session.is_active is False
    
    def test_conversation_flow_integration(self):
        """完全な会話フローの統合テスト"""
        # 1. プレイヤー1が会話を開始
        start_command = StartSpotConversationCommand("tavern_01")
        start_result = start_command.execute(self.player1, self.game_context)
        assert start_result.success is True
        session_id = start_result.session_id
        assert start_result.participants is not None
        assert start_result.history is not None
        
        # 2. プレイヤー2が会話に参加
        join_command = JoinSpotConversationCommand("tavern_01")
        join_result = join_command.execute(self.player2, self.game_context)
        assert join_result.success is True
        assert join_result.session_id == session_id
        assert join_result.participants is not None
        assert join_result.history is not None
        
        # 3. プレイヤー1が発言
        speak1_command = SpeakInConversationCommand("こんにちは！")
        speak1_result = speak1_command.execute(self.player1, self.game_context)
        assert speak1_result.success is True
        assert speak1_result.participants is not None
        assert speak1_result.history is not None
        
        # 4. プレイヤー2が発言
        speak2_command = SpeakInConversationCommand("よろしくお願いします！")
        speak2_result = speak2_command.execute(self.player2, self.game_context)
        assert speak2_result.success is True
        assert speak2_result.participants is not None
        assert speak2_result.history is not None
        
        # 5. 会話履歴に発言内容が含まれていることを確認
        assert "こんにちは！" in speak2_result.history
        assert "よろしくお願いします！" in speak2_result.history
        
        # 6. 参加者リストを確認
        actual_participants = [p for p in speak2_result.participants if p != "System"]
        assert len(actual_participants) == 2
        
        # 7. プレイヤー1が離脱
        leave_command = LeaveConversationCommand()
        leave_result = leave_command.execute(self.player1, self.game_context)
        assert leave_result.success is True
        assert leave_result.participants is not None
        assert leave_result.history is not None
        
        # 8. プレイヤー2が離脱（セッション終了）
        leave2_command = LeaveConversationCommand()
        leave2_result = leave2_command.execute(self.player2, self.game_context)
        assert leave2_result.success is True
        assert leave2_result.participants is not None
        assert leave2_result.history is not None
        
        # 9. セッションが終了していることを確認
        session = self.conversation_manager.sessions.get(session_id)
        assert session is None or session.is_active is False
    
    def test_system_messages_recording(self):
        """システムメッセージ記録のテスト"""
        # プレイヤー1が会話を開始
        start_command = StartSpotConversationCommand("tavern_01")
        start_result = start_command.execute(self.player1, self.game_context)
        assert start_result.success is True
        
        # プレイヤー2が会話に参加
        join_command = JoinSpotConversationCommand("tavern_01")
        join_result = join_command.execute(self.player2, self.game_context)
        assert join_result.success is True
        
        # プレイヤー1が離脱
        leave_command = LeaveConversationCommand()
        leave_result = leave_command.execute(self.player1, self.game_context)
        assert leave_result.success is True
        
        # システムメッセージが記録されていることを確認
        session = self.conversation_manager.sessions.get(join_result.session_id)
        history = session.get_conversation_history()
        
        # 開始、参加、離脱のシステムメッセージが記録されている
        system_messages = [msg for msg in history if msg.sender_id == "System"]
        assert len(system_messages) >= 3  # 開始、参加、離脱メッセージ
        
        # システムメッセージの内容を確認
        system_message_contents = [msg.content for msg in system_messages]
        assert any("会話を開始しました" in content for content in system_message_contents)
        assert any("会話に参加しました" in content for content in system_message_contents)
        assert any("会話から離脱しました" in content for content in system_message_contents)
    
    def test_conversation_manager_not_available(self):
        """会話マネージャーが利用できない場合のテスト"""
        # 会話マネージャーなしでゲームコンテキストを作成
        game_context_no_conversation = GameContext(
            player_manager=self.player_manager,
            spot_manager=self.spot_manager,
            conversation_manager=None
        )
        
        # 各アクションがエラーを返すことを確認
        commands = [
            StartSpotConversationCommand("tavern_01"),
            StartPrivateConversationCommand("player_002", "tavern_01"),
            JoinSpotConversationCommand("tavern_01"),
            SpeakInConversationCommand("こんにちは！"),
            LeaveConversationCommand()
        ]
        
        for command in commands:
            result = command.execute(self.player1, game_context_no_conversation)
            assert result.success is False
            assert "会話システムが利用できません" in result.message
            assert result.participants == []
            assert result.history == "" 