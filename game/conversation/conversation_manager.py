from typing import Dict, Optional, Set, List
from datetime import datetime
from game.conversation.conversation_data import ConversationSession
from game.conversation.message_data import LocationChatMessage


class ConversationManager:
    """
    会話システムの管理クラス
    
    - スポット毎の会話セッション管理
    - 会話状態の追跡
    - 将来的なターン制御機能の基盤
    """
    
    def __init__(self):
        self.sessions: Dict[str, ConversationSession] = {}  # session_id -> ConversationSession
        self.spot_sessions: Dict[str, str] = {}  # spot_id -> session_id
        self.player_sessions: Dict[str, str] = {}  # player_id -> session_id
        self.session_counter: int = 0
    
    def _generate_session_id(self) -> str:
        """新しいセッションIDを生成"""
        self.session_counter += 1
        return f"session_{self.session_counter:04d}"
    
    def start_conversation_session(self, spot_id: str, initiator_player_id: str, is_private: bool = False) -> str:
        """
        会話セッションを開始
        
        Args:
            spot_id: 会話が行われるスポットID
            initiator_player_id: 会話を開始したプレイヤーID
            is_private: 個人宛のセッションかどうか
            
        Returns:
            作成されたセッションID
        """
        # 個人宛のセッションの場合は、既存セッションをチェックしない
        if not is_private and spot_id in self.spot_sessions:
            session_id = self.spot_sessions[spot_id]
            session = self.sessions[session_id]
            session.add_participant(initiator_player_id)
            self.player_sessions[initiator_player_id] = session_id
            return session_id
        
        # 新しいセッションを作成
        session_id = self._generate_session_id()
        session = ConversationSession(
            session_id=session_id,
            spot_id=spot_id,
            participants={initiator_player_id},
            start_time=datetime.now(),
            last_activity=datetime.now(),
            is_private=is_private
        )
        
        self.sessions[session_id] = session
        # 個人宛のセッションはspot_sessionsに登録しない
        if not is_private:
            self.spot_sessions[spot_id] = session_id
        self.player_sessions[initiator_player_id] = session_id
        
        return session_id
    
    def join_conversation(self, player_id: str, spot_id: str) -> Optional[str]:
        """
        既存の会話セッションに参加（個人宛のセッションには参加できない）
        
        Args:
            player_id: 参加するプレイヤーID
            spot_id: 現在いるスポットID
            
        Returns:
            参加したセッションID（セッションが存在しない場合はNone）
        """
        if spot_id not in self.spot_sessions:
            return None
        
        session_id = self.spot_sessions[spot_id]
        session = self.sessions[session_id]
        
        # 個人宛のセッションには参加できない
        if session.is_private:
            return None
        
        if session.is_active:
            session.add_participant(player_id)
            self.player_sessions[player_id] = session_id
            return session_id
        
        return None
    
    def leave_conversation(self, player_id: str):
        """
        会話セッションから離脱
        
        Args:
            player_id: 離脱するプレイヤーID
        """
        if player_id not in self.player_sessions:
            return
        
        session_id = self.player_sessions[player_id]
        session = self.sessions[session_id]
        
        session.remove_participant(player_id)
        del self.player_sessions[player_id]
        
        # セッションが終了した場合は関連データを削除
        if not session.is_active:
            self._cleanup_session(session_id)
    
    def record_message(self, message: LocationChatMessage) -> Optional[str]:
        """
        メッセージを記録し、関連セッションを更新
        
        Args:
            message: 記録するメッセージ
            
        Returns:
            関連するセッションID（セッションが存在しない場合はNone）
        """
        spot_id = message.get_spot_id()
        sender_id = message.sender_id
        
        # まず、送信者が既に参加しているセッションを探す
        if sender_id in self.player_sessions:
            session_id = self.player_sessions[sender_id]
            session = self.sessions[session_id]
            
            # 同じスポットのセッションであれば、そのセッションにメッセージを追加
            if session.spot_id == spot_id and session.is_active:
                session.update_activity()
                session.add_message_to_history(message)
                return session_id
        
        # 送信者が参加していない場合は、スポットの公開セッションを探す
        if spot_id in self.spot_sessions:
            session_id = self.spot_sessions[spot_id]
            session = self.sessions[session_id]
            
            # 個人宛のセッションでない場合のみ参加
            if not session.is_private and session.is_active:
                session.add_participant(sender_id)
                self.player_sessions[sender_id] = session_id
                session.update_activity()
                session.add_message_to_history(message)
                return session_id
        
        # セッションが存在しない場合は自動で作成
        session_id = self.start_conversation_session(spot_id, sender_id)
        session = self.sessions[session_id]
        session.add_message_to_history(message)
        
        return session_id
    
    def get_active_session_for_spot(self, spot_id: str) -> Optional[ConversationSession]:
        """
        指定されたスポットのアクティブな会話セッションを取得（個人宛のセッションは除外）
        
        Args:
            spot_id: スポットID
            
        Returns:
            アクティブなセッション（存在しない場合はNone）
        """
        if spot_id not in self.spot_sessions:
            return None
        
        session_id = self.spot_sessions[spot_id]
        session = self.sessions[session_id]
        
        # 個人宛のセッションは除外
        if session.is_private:
            return None
        
        return session if session.is_active else None
    
    def get_session_participants(self, session_id: str) -> Set[str]:
        """
        セッションの参加者リストを取得
        
        Args:
            session_id: セッションID
            
        Returns:
            参加者のプレイヤーIDセット
        """
        if session_id not in self.sessions:
            return set()
        
        return self.sessions[session_id].participants.copy()
    
    def is_player_in_conversation(self, player_id: str) -> bool:
        """
        プレイヤーが会話に参加しているかチェック
        
        Args:
            player_id: プレイヤーID
            
        Returns:
            会話に参加している場合True
        """
        return player_id in self.player_sessions
    
    def start_private_conversation(self, player_id: str, spot_id: str) -> str:
        """
        個人宛の会話セッションを開始
        
        Args:
            player_id: 会話を開始するプレイヤーID
            spot_id: 会話が行われるスポットID
            
        Returns:
            作成されたセッションID
        """
        return self.start_conversation_session(spot_id, player_id, is_private=True)
    
    def get_player_private_sessions(self, player_id: str) -> List[ConversationSession]:
        """
        プレイヤーの個人宛セッションを取得
        
        Args:
            player_id: プレイヤーID
            
        Returns:
            個人宛セッションのリスト
        """
        private_sessions = []
        for session in self.sessions.values():
            if session.is_private and session.is_active and player_id in session.participants:
                private_sessions.append(session)
        return private_sessions
    
    def get_conversation_history(self, session_id: str) -> List[LocationChatMessage]:
        """
        セッションの会話履歴を取得
        
        Args:
            session_id: セッションID
            
        Returns:
            会話履歴のリスト
        """
        if session_id not in self.sessions:
            return []
        
        session = self.sessions[session_id]
        return session.get_conversation_history()
    
    def get_conversation_history_as_text(self, session_id: str, max_messages: Optional[int] = None) -> str:
        """
        セッションの会話履歴を文字列として取得
        
        Args:
            session_id: セッションID
            max_messages: 取得する最大メッセージ数
            
        Returns:
            会話履歴の文字列表現
        """
        if session_id not in self.sessions:
            return "セッションが見つかりません。"
        
        session = self.sessions[session_id]
        return session.get_conversation_history_as_text(max_messages)
    
    def get_recent_messages(self, session_id: str, count: int = 10) -> List[LocationChatMessage]:
        """
        セッションの最近のメッセージを取得
        
        Args:
            session_id: セッションID
            count: 取得するメッセージ数
            
        Returns:
            最近のメッセージのリスト
        """
        if session_id not in self.sessions:
            return []
        
        session = self.sessions[session_id]
        return session.get_recent_messages(count)
    
    def clear_conversation_history(self, session_id: str):
        """
        セッションの会話履歴をクリア
        
        Args:
            session_id: セッションID
        """
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.clear_history()
    
    def _cleanup_session(self, session_id: str):
        """
        セッション終了時のクリーンアップ
        
        Args:
            session_id: 終了するセッションID
        """
        if session_id not in self.sessions:
            return
        
        session = self.sessions[session_id]
        
        # 関連データを削除
        if session.spot_id in self.spot_sessions:
            del self.spot_sessions[session.spot_id]
        
        # 参加者のセッション情報を削除
        for player_id in list(session.participants):
            if player_id in self.player_sessions:
                del self.player_sessions[player_id]
        
        # セッション自体を削除
        del self.sessions[session_id]
    
    def cleanup_inactive_sessions(self, timeout_minutes: int = 30):
        """
        非アクティブなセッションをクリーンアップ
        
        Args:
            timeout_minutes: タイムアウトまでの分数
        """
        from datetime import timedelta
        
        current_time = datetime.now()
        timeout_delta = timedelta(minutes=timeout_minutes)
        
        sessions_to_cleanup = []
        
        for session_id, session in self.sessions.items():
            if current_time - session.last_activity > timeout_delta:
                sessions_to_cleanup.append(session_id)
        
        for session_id in sessions_to_cleanup:
            self._cleanup_session(session_id)
    
    def get_conversation_stats(self) -> Dict:
        """
        会話システムの統計情報を取得
        
        Returns:
            統計情報の辞書
        """
        active_sessions = sum(1 for session in self.sessions.values() if session.is_active)
        total_participants = sum(len(session.participants) for session in self.sessions.values() if session.is_active)
        
        return {
            "active_sessions": active_sessions,
            "total_sessions": len(self.sessions),
            "total_participants": total_participants,
            "spots_with_conversations": len(self.spot_sessions)
        } 