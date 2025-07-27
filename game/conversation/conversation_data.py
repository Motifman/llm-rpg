from dataclasses import dataclass
from datetime import datetime
from typing import Set


@dataclass
class ConversationSession:
    """会話セッション情報"""
    session_id: str
    spot_id: str
    participants: Set[str]  # 参加プレイヤーのID
    start_time: datetime
    last_activity: datetime
    is_active: bool = True
    
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