"""
会話システムの管理クラス

このモジュールは、エージェント間の会話セッション管理、
会話状態の追跡、将来のターン制御機能を提供します。
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime
from ..systems.message import LocationChatMessage


@dataclass
class ConversationSession:
    """会話セッション情報"""
    session_id: str
    spot_id: str
    participants: Set[str]  # 参加エージェントのID
    start_time: datetime
    last_activity: datetime
    is_active: bool = True
    
    def add_participant(self, agent_id: str):
        """参加者を追加"""
        self.participants.add(agent_id)
        self.last_activity = datetime.now()
    
    def remove_participant(self, agent_id: str):
        """参加者を削除"""
        self.participants.discard(agent_id)
        self.last_activity = datetime.now()
        
        # 参加者がいなくなった場合はセッション終了
        if not self.participants:
            self.is_active = False
    
    def update_activity(self):
        """最終活動時刻を更新"""
        self.last_activity = datetime.now()


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
        self.agent_sessions: Dict[str, str] = {}  # agent_id -> session_id
        self.session_counter: int = 0
    
    def _generate_session_id(self) -> str:
        """新しいセッションIDを生成"""
        self.session_counter += 1
        return f"session_{self.session_counter:04d}"
    
    def start_conversation_session(self, spot_id: str, initiator_agent_id: str) -> str:
        """
        会話セッションを開始
        
        Args:
            spot_id: 会話が行われるスポットID
            initiator_agent_id: 会話を開始したエージェントID
            
        Returns:
            作成されたセッションID
        """
        # 既存のセッションがある場合は参加者として追加
        if spot_id in self.spot_sessions:
            session_id = self.spot_sessions[spot_id]
            session = self.sessions[session_id]
            session.add_participant(initiator_agent_id)
            self.agent_sessions[initiator_agent_id] = session_id
            return session_id
        
        # 新しいセッションを作成
        session_id = self._generate_session_id()
        session = ConversationSession(
            session_id=session_id,
            spot_id=spot_id,
            participants={initiator_agent_id},
            start_time=datetime.now(),
            last_activity=datetime.now()
        )
        
        self.sessions[session_id] = session
        self.spot_sessions[spot_id] = session_id
        self.agent_sessions[initiator_agent_id] = session_id
        
        return session_id
    
    def join_conversation(self, agent_id: str, spot_id: str) -> Optional[str]:
        """
        既存の会話セッションに参加
        
        Args:
            agent_id: 参加するエージェントID
            spot_id: 現在いるスポットID
            
        Returns:
            参加したセッションID（セッションが存在しない場合はNone）
        """
        if spot_id not in self.spot_sessions:
            return None
        
        session_id = self.spot_sessions[spot_id]
        session = self.sessions[session_id]
        
        if session.is_active:
            session.add_participant(agent_id)
            self.agent_sessions[agent_id] = session_id
            return session_id
        
        return None
    
    def leave_conversation(self, agent_id: str):
        """
        会話セッションから離脱
        
        Args:
            agent_id: 離脱するエージェントID
        """
        if agent_id not in self.agent_sessions:
            return
        
        session_id = self.agent_sessions[agent_id]
        session = self.sessions[session_id]
        
        session.remove_participant(agent_id)
        del self.agent_sessions[agent_id]
        
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
        
        # セッションが存在しない場合は自動で作成
        if spot_id not in self.spot_sessions:
            session_id = self.start_conversation_session(spot_id, message.sender_id)
        else:
            session_id = self.spot_sessions[spot_id]
            session = self.sessions[session_id]
            session.update_activity()
        
        return session_id
    
    def get_active_session_for_spot(self, spot_id: str) -> Optional[ConversationSession]:
        """
        指定されたスポットのアクティブな会話セッションを取得
        
        Args:
            spot_id: スポットID
            
        Returns:
            アクティブなセッション（存在しない場合はNone）
        """
        if spot_id not in self.spot_sessions:
            return None
        
        session_id = self.spot_sessions[spot_id]
        session = self.sessions[session_id]
        
        return session if session.is_active else None
    
    def get_session_participants(self, session_id: str) -> Set[str]:
        """
        セッションの参加者リストを取得
        
        Args:
            session_id: セッションID
            
        Returns:
            参加者のエージェントIDセット
        """
        if session_id not in self.sessions:
            return set()
        
        return self.sessions[session_id].participants.copy()
    
    def is_agent_in_conversation(self, agent_id: str) -> bool:
        """
        エージェントが会話に参加しているかチェック
        
        Args:
            agent_id: エージェントID
            
        Returns:
            会話に参加している場合True
        """
        return agent_id in self.agent_sessions
    
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
        for agent_id in list(session.participants):
            if agent_id in self.agent_sessions:
                del self.agent_sessions[agent_id]
        
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