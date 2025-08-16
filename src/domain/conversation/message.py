from dataclasses import dataclass
from datetime import datetime
import uuid


@dataclass(frozen=True)
class Message:
    message_id: int
    sender_id: int
    sender_name: str
    recipient_id: int
    content: str
    timestamp: datetime

    @classmethod
    def create(cls, sender_id: int, sender_name: str, recipient_id: int, content: str, timestamp: datetime) -> "Message":
        """
        メッセージを生成するファクトリメソッド
        """
        message_id = uuid.uuid4()
        if not content:
            raise ValueError("メッセージ内容は空にできません。")
        return cls(message_id=message_id, sender_id=sender_id, sender_name=sender_name, recipient_id=recipient_id, content=content, timestamp=timestamp)

    def display(self) -> str:
        return f"{self.sender_name}: {self.content}"