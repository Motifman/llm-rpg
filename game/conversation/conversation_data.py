from dataclasses import dataclass
from datetime import datetime
from typing import Set, List, Optional
from game.conversation.message_data import LocationChatMessage, ChatMessage


@dataclass
class ConversationSession:
    """会話セッション情報"""
    session_id: str
    spot_id: str
    participants: Set[str]  # 参加プレイヤーのID
    start_time: datetime
    last_activity: datetime
    is_active: bool = True
    is_private: bool = False  # 個人宛のセッションかどうか
    conversation_history: List[LocationChatMessage] = None  # 会話履歴
    
    def add_participant(self, player_id: str):
        """参加者を追加"""
        self.participants.add(player_id)
        self.last_activity = datetime.now()
    
    def remove_participant(self, player_id: str):
        """参加者を削除"""
        self.participants.discard(player_id)
        self.last_activity = datetime.now()
        
        # 参加者がいなくなった場合はセッション終了
        if not self.participants:
            self.is_active = False
    
    def update_activity(self):
        """最終活動時刻を更新"""
        self.last_activity = datetime.now()
    
    def add_message_to_history(self, message: LocationChatMessage):
        """会話履歴にメッセージを追加"""
        if self.conversation_history is None:
            self.conversation_history = []
        self.conversation_history.append(message)
        self.last_activity = datetime.now()
    
    def get_conversation_history(self) -> List[LocationChatMessage]:
        """会話履歴を取得"""
        return self.conversation_history or []
    
    def get_conversation_history_as_text(self, max_messages: Optional[int] = None) -> str:
        """会話履歴をチャットアプリのトーク履歴のような文字列に変換"""
        if not self.conversation_history:
            return "会話履歴がありません。"
        
        messages = self.conversation_history
        if max_messages:
            messages = messages[-max_messages:]
        
        history_text = []
        for message in messages:
            timestamp = message.timestamp
            sender = message.sender_id
            content = message.content
            
            # 時刻を読みやすい形式に変換
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime("%H:%M")
            except:
                formatted_time = "??:??"
            
            history_text.append(f"[{formatted_time}] {sender}: {content}")
        
        return "\n".join(history_text)
    
    def get_recent_messages(self, count: int = 10) -> List[LocationChatMessage]:
        """最近のメッセージを取得"""
        if not self.conversation_history:
            return []
        return self.conversation_history[-count:]
    
    def clear_history(self):
        """会話履歴をクリア"""
        self.conversation_history = []