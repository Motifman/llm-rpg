import pytest
from datetime import datetime, timedelta
from game.conversation.conversation_manager import ConversationManager
from game.conversation.conversation_data import ConversationSession
from game.conversation.message_data import (
    LocationChatMessage, 
    ChatMessage, 
    WhisperChatMessage, 
    SystemNotification, 
    GameEventMessage
)


class TestConversationManager:
    """ConversationManagerのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.manager = ConversationManager()
        
        # テスト用データ
        self.spot_id = "tavern_01"
        self.player1_id = "player_001"
        self.player2_id = "player_002"
        self.player3_id = "player_003"
    
    # === セッション管理のテスト ===
    
    def test_start_conversation_session_new(self):
        """新しい会話セッション開始のテスト"""
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        assert session_id is not None
        assert session_id.startswith("session_")
        
        # セッションが正しく作成されているかチェック
        session = self.manager.sessions[session_id]
        assert session.spot_id == self.spot_id
        assert self.player1_id in session.participants
        assert session.is_active is True
        
        # スポットとプレイヤーのマッピングが正しいかチェック
        assert self.manager.spot_sessions[self.spot_id] == session_id
        assert self.manager.player_sessions[self.player1_id] == session_id
    
    def test_start_conversation_session_existing(self):
        """既存セッションへの参加テスト"""
        # 最初のセッションを作成
        session_id1 = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # 同じスポットで新しいプレイヤーがセッション開始
        session_id2 = self.manager.start_conversation_session(self.spot_id, self.player2_id)
        
        # 同じセッションIDが返される
        assert session_id1 == session_id2
        
        # 両方のプレイヤーが参加者リストに含まれている
        session = self.manager.sessions[session_id1]
        assert self.player1_id in session.participants
        assert self.player2_id in session.participants
        assert len(session.participants) == 2
    
    def test_join_conversation_success(self):
        """既存セッションへの参加テスト"""
        # セッションを作成
        self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # 別のプレイヤーが参加
        session_id = self.manager.join_conversation(self.player2_id, self.spot_id)
        
        assert session_id is not None
        session = self.manager.sessions[session_id]
        assert self.player2_id in session.participants
        assert self.manager.player_sessions[self.player2_id] == session_id
    
    def test_join_conversation_nonexistent(self):
        """存在しないセッションへの参加テスト"""
        session_id = self.manager.join_conversation(self.player1_id, self.spot_id)
        assert session_id is None
    
    def test_leave_conversation(self):
        """セッションからの離脱テスト"""
        # セッションを作成して参加者を追加
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        self.manager.join_conversation(self.player2_id, self.spot_id)
        
        # プレイヤー1が離脱
        self.manager.leave_conversation(self.player1_id)
        
        # プレイヤー1のセッション情報が削除されている
        assert self.player1_id not in self.manager.player_sessions
        
        # セッションはまだアクティブ（プレイヤー2が残っている）
        session = self.manager.sessions[session_id]
        assert session.is_active is True
        assert self.player1_id not in session.participants
        assert self.player2_id in session.participants
    
    def test_leave_conversation_session_end(self):
        """最後の参加者が離脱した時のセッション終了テスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # 唯一の参加者が離脱
        self.manager.leave_conversation(self.player1_id)
        
        # セッションが終了している
        session = self.manager.sessions.get(session_id)
        assert session is None or session.is_active is False
        
        # 関連データがクリーンアップされている
        assert self.spot_id not in self.manager.spot_sessions
        assert self.player1_id not in self.manager.player_sessions
    
    def test_leave_conversation_nonexistent_player(self):
        """存在しないプレイヤーの離脱テスト"""
        # 存在しないプレイヤーが離脱を試行
        self.manager.leave_conversation("nonexistent_player")
        # エラーが発生しないことを確認
    
    def test_join_conversation_inactive_session(self):
        """非アクティブセッションへの参加テスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # セッションを非アクティブにする
        session = self.manager.sessions[session_id]
        session.is_active = False
        
        # 非アクティブセッションへの参加は失敗する
        result = self.manager.join_conversation(self.player2_id, self.spot_id)
        assert result is None
    
    # === メッセージ記録のテスト ===
    
    def test_record_message_new_session(self):
        """新しいセッションでのメッセージ記録テスト"""
        message = LocationChatMessage(self.player1_id, self.spot_id, "こんにちは！")
        session_id = self.manager.record_message(message)
        
        assert session_id is not None
        session = self.manager.sessions[session_id]
        assert session.spot_id == self.spot_id
        assert self.player1_id in session.participants
    
    def test_record_message_existing_session(self):
        """既存セッションでのメッセージ記録テスト"""
        # セッションを作成
        original_session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # メッセージを記録
        message = LocationChatMessage(self.player2_id, self.spot_id, "こんにちは！")
        session_id = self.manager.record_message(message)
        
        assert session_id == original_session_id
        session = self.manager.sessions[session_id]
        # record_messageは新しいプレイヤーを自動的に参加者として追加する
        assert self.player2_id in session.participants
        assert self.player1_id in session.participants
        assert len(session.participants) == 2
    
    # === セッション情報取得のテスト ===
    
    def test_get_active_session_for_spot(self):
        """スポットのアクティブセッション取得テスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # アクティブセッションを取得
        session = self.manager.get_active_session_for_spot(self.spot_id)
        assert session is not None
        assert session.session_id == session_id
        assert session.is_active is True
    
    def test_get_active_session_for_spot_nonexistent(self):
        """存在しないスポットのセッション取得テスト"""
        session = self.manager.get_active_session_for_spot(self.spot_id)
        assert session is None
    
    def test_get_session_participants(self):
        """セッション参加者リスト取得テスト"""
        # セッションを作成して参加者を追加
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        self.manager.join_conversation(self.player2_id, self.spot_id)
        
        participants = self.manager.get_session_participants(session_id)
        assert self.player1_id in participants
        assert self.player2_id in participants
        assert len(participants) == 2
    
    def test_get_session_participants_nonexistent(self):
        """存在しないセッションの参加者取得テスト"""
        participants = self.manager.get_session_participants("nonexistent_session")
        assert participants == set()
    
    def test_is_player_in_conversation(self):
        """プレイヤーの会話参加状態チェックテスト"""
        # プレイヤー1がセッションに参加
        self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        assert self.manager.is_player_in_conversation(self.player1_id) is True
        assert self.manager.is_player_in_conversation(self.player2_id) is False
    
    # === クリーンアップのテスト ===
    
    def test_cleanup_inactive_sessions(self):
        """非アクティブセッションのクリーンアップテスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # セッションを非アクティブにする（時間を過去に設定）
        session = self.manager.sessions[session_id]
        session.last_activity = datetime.now() - timedelta(minutes=31)
        
        # クリーンアップを実行
        self.manager.cleanup_inactive_sessions(timeout_minutes=30)
        
        # セッションが削除されている
        assert session_id not in self.manager.sessions
        assert self.spot_id not in self.manager.spot_sessions
        assert self.player1_id not in self.manager.player_sessions
    
    def test_cleanup_active_sessions(self):
        """アクティブセッションはクリーンアップされないテスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # クリーンアップを実行
        self.manager.cleanup_inactive_sessions(timeout_minutes=30)
        
        # セッションは残っている
        assert session_id in self.manager.sessions
        assert self.spot_id in self.manager.spot_sessions
        assert self.player1_id in self.manager.player_sessions
    
    def test_cleanup_nonexistent_session(self):
        """存在しないセッションのクリーンアップテスト"""
        # 存在しないセッションIDでクリーンアップを実行
        self.manager._cleanup_session("nonexistent_session")
        # エラーが発生しないことを確認
    
    def test_get_active_session_for_spot_inactive_session(self):
        """非アクティブセッションの取得テスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # セッションを非アクティブにする
        session = self.manager.sessions[session_id]
        session.is_active = False
        
        # 非アクティブセッションは取得されない
        result = self.manager.get_active_session_for_spot(self.spot_id)
        assert result is None
    
    # === 統計情報のテスト ===
    
    def test_get_conversation_stats(self):
        """会話統計情報取得テスト"""
        # 複数のセッションを作成
        self.manager.start_conversation_session("spot_1", self.player1_id)
        self.manager.start_conversation_session("spot_2", self.player2_id)
        self.manager.join_conversation(self.player3_id, "spot_1")
        
        stats = self.manager.get_conversation_stats()
        
        assert stats["active_sessions"] == 2
        assert stats["total_sessions"] == 2
        assert stats["total_participants"] == 3
        assert stats["spots_with_conversations"] == 2
    
    def test_get_conversation_stats_empty(self):
        """空の状態での統計情報取得テスト"""
        stats = self.manager.get_conversation_stats()
        
        assert stats["active_sessions"] == 0
        assert stats["total_sessions"] == 0
        assert stats["total_participants"] == 0
        assert stats["spots_with_conversations"] == 0


class TestConversationSession:
    """ConversationSessionのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.session_id = "test_session_001"
        self.spot_id = "test_spot_001"
        self.participants = {"player_001", "player_002"}
        self.start_time = datetime.now()
        self.last_activity = datetime.now()
        
        self.session = ConversationSession(
            session_id=self.session_id,
            spot_id=self.spot_id,
            participants=self.participants.copy(),
            start_time=self.start_time,
            last_activity=self.last_activity
        )
    
    def test_conversation_session_creation(self):
        """ConversationSession作成テスト"""
        assert self.session.session_id == self.session_id
        assert self.session.spot_id == self.spot_id
        assert self.session.participants == self.participants
        assert self.session.start_time == self.start_time
        assert self.session.last_activity == self.last_activity
        assert self.session.is_active is True
    
    def test_add_participant(self):
        """参加者追加テスト"""
        new_player = "player_003"
        original_activity = self.session.last_activity
        
        # 少し時間を進める
        import time
        time.sleep(0.001)
        
        self.session.add_participant(new_player)
        
        assert new_player in self.session.participants
        assert len(self.session.participants) == 3
        assert self.session.last_activity > original_activity
    
    def test_remove_participant(self):
        """参加者削除テスト"""
        player_to_remove = "player_001"
        original_activity = self.session.last_activity
        
        # 少し時間を進める
        import time
        time.sleep(0.001)
        
        self.session.remove_participant(player_to_remove)
        
        assert player_to_remove not in self.session.participants
        assert len(self.session.participants) == 1
        assert self.session.last_activity > original_activity
        assert self.session.is_active is True  # まだ参加者がいる
    
    def test_remove_participant_session_end(self):
        """最後の参加者削除時のセッション終了テスト"""
        # 参加者を1人ずつ削除
        self.session.remove_participant("player_001")
        assert self.session.is_active is True
        
        self.session.remove_participant("player_002")
        assert self.session.is_active is False
        assert len(self.session.participants) == 0
    
    def test_update_activity(self):
        """活動時刻更新テスト"""
        original_activity = self.session.last_activity
        
        # 少し時間を進める
        import time
        time.sleep(0.001)
        
        self.session.update_activity()
        
        assert self.session.last_activity > original_activity
    
    def test_add_message_to_history(self):
        """会話履歴にメッセージ追加テスト"""
        message = LocationChatMessage("player_003", "test_spot_002", "テストメッセージ")
        
        self.session.add_message_to_history(message)
        
        history = self.session.get_conversation_history()
        assert len(history) == 1
        assert history[0].content == "テストメッセージ"
        assert history[0].sender_id == "player_003"
    
    def test_get_conversation_history_as_text(self):
        """会話履歴の文字列変換テスト"""
        # メッセージを追加
        messages = [
            LocationChatMessage("player_001", "test_spot_001", "こんにちは！"),
            LocationChatMessage("player_002", "test_spot_001", "よろしくお願いします！")
        ]
        
        for message in messages:
            self.session.add_message_to_history(message)
        
        # 文字列として履歴を取得
        history_text = self.session.get_conversation_history_as_text()
        assert "こんにちは！" in history_text
        assert "よろしくお願いします！" in history_text
        assert "player_001" in history_text
        assert "player_002" in history_text
    
    def test_get_conversation_history_as_text_with_limit(self):
        """制限付き会話履歴の文字列変換テスト"""
        # 複数のメッセージを追加
        for i in range(5):
            message = LocationChatMessage(f"player_{i}", "test_spot_001", f"メッセージ{i}")
            self.session.add_message_to_history(message)
        
        # 最近の3件のみを文字列として取得
        history_text = self.session.get_conversation_history_as_text(max_messages=3)
        assert "メッセージ2" in history_text
        assert "メッセージ3" in history_text
        assert "メッセージ4" in history_text
        assert "メッセージ0" not in history_text
        assert "メッセージ1" not in history_text
    
    def test_get_recent_messages(self):
        """最近のメッセージ取得テスト"""
        # 複数のメッセージを追加
        for i in range(10):
            message = LocationChatMessage(f"player_{i}", "test_spot_001", f"メッセージ{i}")
            self.session.add_message_to_history(message)
        
        # 最近の5件を取得
        recent_messages = self.session.get_recent_messages(5)
        assert len(recent_messages) == 5
        assert recent_messages[-1].content == "メッセージ9"
        assert recent_messages[0].content == "メッセージ5"
    
    def test_clear_history(self):
        """会話履歴クリアテスト"""
        # メッセージを追加
        message = LocationChatMessage("player_001", "test_spot_001", "テストメッセージ")
        self.session.add_message_to_history(message)
        
        # 履歴をクリア
        self.session.clear_history()
        
        # 履歴が空になっていることを確認
        history = self.session.get_conversation_history()
        assert len(history) == 0


class TestMessageData:
    """メッセージデータクラスのテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.sender_id = "player_001"
        self.recipient_id = "player_002"
        self.spot_id = "tavern_01"
        self.content = "こんにちは！"
    
    def test_location_chat_message_creation(self):
        """LocationChatMessage作成テスト"""
        message = LocationChatMessage(self.sender_id, self.spot_id, self.content)
        
        assert message.sender_id == self.sender_id
        assert message.spot_id == self.spot_id
        assert message.content == self.content
        assert message.target_player_id is None
        assert message.message_id is not None
        assert message.timestamp is not None
        assert message.message_type == "LocationChatMessage"
    
    def test_location_chat_message_with_target(self):
        """特定プレイヤー向けLocationChatMessage作成テスト"""
        message = LocationChatMessage(self.sender_id, self.spot_id, self.content, self.recipient_id)
        
        assert message.target_player_id == self.recipient_id
        assert message.is_broadcast() is False
        assert message.is_targeted() is True
        assert message.get_target_player_id() == self.recipient_id
    
    def test_location_chat_message_broadcast(self):
        """全体向けLocationChatMessage作成テスト"""
        message = LocationChatMessage(self.sender_id, self.spot_id, self.content)
        
        assert message.is_broadcast() is True
        assert message.is_targeted() is False
        assert message.get_spot_id() == self.spot_id
    
    def test_chat_message_creation(self):
        """ChatMessage作成テスト"""
        message = ChatMessage(self.sender_id, self.content)
        
        assert message.sender_id == self.sender_id
        assert message.content == self.content
        assert message.message_id is not None
        assert message.timestamp is not None
        assert message.message_type == "ChatMessage"
    
    def test_whisper_chat_message_creation(self):
        """WhisperChatMessage作成テスト"""
        message = WhisperChatMessage(self.sender_id, self.recipient_id, self.content)
        
        assert message.sender_id == self.sender_id
        assert message.recipient_id == self.recipient_id
        assert message.content == self.content
        assert message.message_type == "WhisperChatMessage"
    
    def test_system_notification_creation(self):
        """SystemNotification作成テスト"""
        notification_type = "TASK_COMPLETED"
        details = {"task_name": "テストクエスト", "reward": 100}
        
        message = SystemNotification(self.recipient_id, notification_type, details)
        
        assert message.sender_id == "System"
        assert message.recipient_id == self.recipient_id
        assert message.notification_type == notification_type
        assert message.details == details
        assert message.message_type == "SystemNotification"
    
    def test_game_event_message_creation(self):
        """GameEventMessage作成テスト"""
        event_type = "ITEM_SPAWNED"
        location_id = "forest_01"
        description = "宝箱が出現しました"
        
        message = GameEventMessage(event_type, location_id, description)
        
        assert message.sender_id == "Environment"
        assert message.recipient_id == "Broadcast"
        assert message.event_type == event_type
        assert message.location_id == location_id
        assert message.description == description
        assert message.message_type == "GameEventMessage"
    
    def test_message_to_dict(self):
        """メッセージの辞書変換テスト"""
        message = LocationChatMessage(self.sender_id, self.spot_id, self.content)
        data = message.to_dict()
        
        assert data["sender_id"] == self.sender_id
        assert data["spot_id"] == self.spot_id
        assert data["content"] == self.content
        assert data["message_type"] == "LocationChatMessage"
        assert "message_id" in data
        assert "timestamp" in data
    
    def test_message_to_json(self):
        """メッセージのJSON変換テスト"""
        message = LocationChatMessage(self.sender_id, self.spot_id, self.content)
        json_str = message.to_json()
        
        assert isinstance(json_str, str)
        assert self.sender_id in json_str
        assert self.spot_id in json_str
        assert self.content in json_str
    
    def test_message_repr(self):
        """メッセージの文字列表現テスト"""
        message = LocationChatMessage(self.sender_id, self.spot_id, self.content)
        repr_str = repr(message)
        
        assert "LocationChatMessage" in repr_str
        assert "id=" in repr_str
        assert message.message_id[:8] in repr_str
    
    def test_message_str(self):
        """メッセージの文字列変換テスト"""
        message = LocationChatMessage(self.sender_id, self.spot_id, self.content)
        str_result = str(message)
        
        assert "LocationChatMessage" in str_result
        assert "id=" in str_result
        assert message.message_id[:8] in str_result
    
    def test_whisper_chat_message_repr(self):
        """WhisperChatMessageの文字列表現テスト"""
        message = WhisperChatMessage(self.sender_id, self.recipient_id, self.content)
        repr_str = repr(message)
        
        assert "WhisperChatMessage" in repr_str
        assert "id=" in repr_str
        assert message.message_id[:8] in repr_str
    
    def test_system_notification_repr(self):
        """SystemNotificationの文字列表現テスト"""
        message = SystemNotification(self.recipient_id, "TEST", {})
        repr_str = repr(message)
        
        assert "SystemNotification" in repr_str
        assert "id=" in repr_str
        assert message.message_id[:8] in repr_str
    
    def test_game_event_message_repr(self):
        """GameEventMessageの文字列表現テスト"""
        message = GameEventMessage("TEST", "location", "description")
        repr_str = repr(message)
        
        assert "GameEventMessage" in repr_str
        assert "id=" in repr_str
        assert message.message_id[:8] in repr_str


class TestConversationSystemIntegration:
    """会話システム統合テスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.manager = ConversationManager()
        self.spot_id = "tavern_01"
        self.player1_id = "player_001"
        self.player2_id = "player_002"
        self.player3_id = "player_003"
    
    def test_conversation_flow(self):
        """完全な会話フローのテスト"""
        # 1. プレイヤー1がセッション開始
        session_id1 = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        assert session_id1 is not None
        
        # 2. プレイヤー1がメッセージ送信
        message1 = LocationChatMessage(self.player1_id, self.spot_id, "こんにちは！")
        session_id2 = self.manager.record_message(message1)
        assert session_id1 == session_id2
        
        # 3. プレイヤー2が参加
        session_id3 = self.manager.join_conversation(self.player2_id, self.spot_id)
        assert session_id1 == session_id3
        
        # 4. プレイヤー2がメッセージ送信
        message2 = LocationChatMessage(self.player2_id, self.spot_id, "よろしくお願いします！")
        session_id4 = self.manager.record_message(message2)
        assert session_id1 == session_id4
        
        # 5. プレイヤー3が参加
        self.manager.join_conversation(self.player3_id, self.spot_id)
        
        # 6. セッション情報確認
        session = self.manager.get_active_session_for_spot(self.spot_id)
        assert session is not None
        assert len(session.participants) == 3
        assert self.player1_id in session.participants
        assert self.player2_id in session.participants
        assert self.player3_id in session.participants
        
        # 7. プレイヤー1が離脱
        self.manager.leave_conversation(self.player1_id)
        assert self.manager.is_player_in_conversation(self.player1_id) is False
        assert self.manager.is_player_in_conversation(self.player2_id) is True
        
        # 8. 残りのプレイヤーが離脱
        self.manager.leave_conversation(self.player2_id)
        self.manager.leave_conversation(self.player3_id)
        
        # 9. セッションが終了していることを確認
        session = self.manager.get_active_session_for_spot(self.spot_id)
        assert session is None
    
    def test_multiple_spots_conversation(self):
        """複数スポットでの会話テスト"""
        spot1 = "tavern_01"
        spot2 = "shop_01"
        
        # スポット1でセッション開始
        session1_id = self.manager.start_conversation_session(spot1, self.player1_id)
        
        # スポット2でセッション開始
        session2_id = self.manager.start_conversation_session(spot2, self.player2_id)
        
        # 異なるセッションID
        assert session1_id != session2_id
        
        # 各スポットのセッション確認
        session1 = self.manager.get_active_session_for_spot(spot1)
        session2 = self.manager.get_active_session_for_spot(spot2)
        
        assert session1.session_id == session1_id
        assert session2.session_id == session2_id
        assert session1.spot_id == spot1
        assert session2.spot_id == spot2
    
    def test_session_timeout_cleanup(self):
        """セッションタイムアウトクリーンアップテスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # セッションを非アクティブにする
        session = self.manager.sessions[session_id]
        session.last_activity = datetime.now() - timedelta(minutes=31)
        
        # クリーンアップ実行
        self.manager.cleanup_inactive_sessions(timeout_minutes=30)
        
        # セッションが削除されていることを確認
        assert session_id not in self.manager.sessions
        assert self.spot_id not in self.manager.spot_sessions
        assert self.player1_id not in self.manager.player_sessions
        
        # 統計情報確認
        stats = self.manager.get_conversation_stats()
        assert stats["active_sessions"] == 0
        assert stats["total_sessions"] == 0
    
    def test_private_conversation_with_history(self):
        """個人宛セッションでの会話履歴テスト"""
        # 個人宛セッションを作成
        session_id = self.manager.start_private_conversation(self.player1_id, self.spot_id)
        
        # メッセージを送信
        message = LocationChatMessage(self.player1_id, self.spot_id, "個人宛メッセージ")
        self.manager.record_message(message)
        
        # 履歴を確認
        history = self.manager.get_conversation_history(session_id)
        assert len(history) == 1
        assert history[0].content == "個人宛メッセージ"
        
        # 文字列として履歴を取得
        history_text = self.manager.get_conversation_history_as_text(session_id)
        assert "個人宛メッセージ" in history_text
    
    def test_mixed_public_and_private_sessions(self):
        """公開セッションと個人宛セッションの混在テスト"""
        # 公開セッションを作成
        public_session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # 個人宛セッションを作成
        private_session_id = self.manager.start_private_conversation(self.player2_id, self.spot_id)
        
        # 公開セッションにメッセージを送信
        public_message = LocationChatMessage(self.player1_id, self.spot_id, "公開メッセージ")
        self.manager.record_message(public_message)
        
        # 個人宛セッションにメッセージを送信
        private_message = LocationChatMessage(self.player2_id, self.spot_id, "個人宛メッセージ")
        self.manager.record_message(private_message)
        
        # 各セッションの履歴を確認
        public_history = self.manager.get_conversation_history(public_session_id)
        private_history = self.manager.get_conversation_history(private_session_id)
        
        assert len(public_history) == 1
        assert len(private_history) == 1
        assert public_history[0].content == "公開メッセージ"
        assert private_history[0].content == "個人宛メッセージ"
        
        # スポットのアクティブセッションは公開セッションのみ
        active_session = self.manager.get_active_session_for_spot(self.spot_id)
        assert active_session is not None
        assert active_session.session_id == public_session_id
        assert not active_session.is_private
    
    # === 個人宛セッションのテスト ===
    
    def test_start_private_conversation(self):
        """個人宛セッション開始テスト"""
        session_id = self.manager.start_private_conversation(self.player1_id, self.spot_id)
        
        assert session_id is not None
        session = self.manager.sessions[session_id]
        assert session.is_private is True
        assert session.spot_id == self.spot_id
        assert self.player1_id in session.participants
        
        # 個人宛セッションはspot_sessionsに登録されない
        assert self.spot_id not in self.manager.spot_sessions
    
    def test_join_private_conversation_fails(self):
        """個人宛セッションへの参加失敗テスト"""
        # 個人宛セッションを作成
        session_id = self.manager.start_private_conversation(self.player1_id, self.spot_id)
        
        # 他のプレイヤーが参加を試行
        result = self.manager.join_conversation(self.player2_id, self.spot_id)
        assert result is None
        
        # セッションは変更されていない
        session = self.manager.sessions[session_id]
        assert len(session.participants) == 1
        assert self.player2_id not in session.participants
    
    def test_get_active_session_for_spot_excludes_private(self):
        """スポットのアクティブセッション取得で個人宛セッションを除外するテスト"""
        # 個人宛セッションを作成
        self.manager.start_private_conversation(self.player1_id, self.spot_id)
        
        # スポットのアクティブセッションを取得
        session = self.manager.get_active_session_for_spot(self.spot_id)
        assert session is None
    
    def test_get_player_private_sessions(self):
        """プレイヤーの個人宛セッション取得テスト"""
        # 個人宛セッションを作成
        session_id = self.manager.start_private_conversation(self.player1_id, self.spot_id)
        
        # プレイヤーの個人宛セッションを取得
        private_sessions = self.manager.get_player_private_sessions(self.player1_id)
        assert len(private_sessions) == 1
        assert private_sessions[0].session_id == session_id
        assert private_sessions[0].is_private is True
    
    def test_get_player_private_sessions_empty(self):
        """プレイヤーの個人宛セッション取得（空の場合）テスト"""
        private_sessions = self.manager.get_player_private_sessions(self.player1_id)
        assert len(private_sessions) == 0
    
    # === 会話履歴のテスト ===
    
    def test_record_message_adds_to_history(self):
        """メッセージ記録が履歴に追加されるテスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # メッセージを送信
        message = LocationChatMessage(self.player1_id, self.spot_id, "こんにちは！")
        self.manager.record_message(message)
        
        # 履歴を確認
        history = self.manager.get_conversation_history(session_id)
        assert len(history) == 1
        assert history[0].content == "こんにちは！"
        assert history[0].sender_id == self.player1_id
    
    def test_conversation_history_multiple_messages(self):
        """複数メッセージの会話履歴テスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # 複数のメッセージを送信
        messages = [
            LocationChatMessage(self.player1_id, self.spot_id, "こんにちは！"),
            LocationChatMessage(self.player2_id, self.spot_id, "よろしくお願いします！"),
            LocationChatMessage(self.player1_id, self.spot_id, "ありがとうございます！")
        ]
        
        for message in messages:
            self.manager.record_message(message)
        
        # 履歴を確認
        history = self.manager.get_conversation_history(session_id)
        assert len(history) == 3
        assert history[0].content == "こんにちは！"
        assert history[1].content == "よろしくお願いします！"
        assert history[2].content == "ありがとうございます！"
    
    def test_get_conversation_history_as_text(self):
        """会話履歴の文字列変換テスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # メッセージを送信
        message = LocationChatMessage(self.player1_id, self.spot_id, "こんにちは！")
        self.manager.record_message(message)
        
        # 文字列として履歴を取得
        history_text = self.manager.get_conversation_history_as_text(session_id)
        assert "こんにちは！" in history_text
        assert self.player1_id in history_text
    
    def test_get_conversation_history_as_text_empty(self):
        """空の会話履歴の文字列変換テスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # 文字列として履歴を取得
        history_text = self.manager.get_conversation_history_as_text(session_id)
        assert "会話履歴がありません" in history_text
    
    def test_get_recent_messages(self):
        """最近のメッセージ取得テスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # 複数のメッセージを送信
        for i in range(15):
            message = LocationChatMessage(self.player1_id, self.spot_id, f"メッセージ{i}")
            self.manager.record_message(message)
        
        # 最近の10件を取得
        recent_messages = self.manager.get_recent_messages(session_id, 10)
        assert len(recent_messages) == 10
        assert recent_messages[-1].content == "メッセージ14"
    
    def test_clear_conversation_history(self):
        """会話履歴クリアテスト"""
        # セッションを作成
        session_id = self.manager.start_conversation_session(self.spot_id, self.player1_id)
        
        # メッセージを送信
        message = LocationChatMessage(self.player1_id, self.spot_id, "こんにちは！")
        self.manager.record_message(message)
        
        # 履歴をクリア
        self.manager.clear_conversation_history(session_id)
        
        # 履歴が空になっていることを確認
        history = self.manager.get_conversation_history(session_id)
        assert len(history) == 0
    
    def test_get_conversation_history_nonexistent_session(self):
        """存在しないセッションの履歴取得テスト"""
        history = self.manager.get_conversation_history("nonexistent_session")
        assert len(history) == 0
    
    def test_get_conversation_history_as_text_nonexistent_session(self):
        """存在しないセッションの履歴文字列取得テスト"""
        history_text = self.manager.get_conversation_history_as_text("nonexistent_session")
        assert "セッションが見つかりません" in history_text 