import abc
import uuid
import datetime
import json


class AbstractMessage(abc.ABC):
    def __init__(self):
        self.message_id: str = str(uuid.uuid4())
        self.timestamp: str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.message_type: str = self.__class__.__name__

    @abc.abstractmethod
    def to_dict(self) -> dict:
        """
        convert to dict
        """
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "message_type": self.message_type,
        }

    def to_json(self) -> str:
        """
        convert to json
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def __repr__(self) -> str:
        """
        debug representation
        """
        return f"{self.message_type}(id={self.message_id[:8]}...)"


class ChatMessage(AbstractMessage):
    """
    ChatMessageは同じ場所にいる全プレイヤーに送信されるメッセージです。
    送信者ID(sender_id)とメッセージ内容(content)を含みます。
    """
    def __init__(self, sender_id: str, content: str):
        super().__init__()
        self.sender_id = sender_id
        self.content = content

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "sender_id": self.sender_id,
            "content": self.content,
            "message_type": self.message_type,
        })
        return data
    
    def __repr__(self) -> str:
        return f"ChatMessage(id={self.message_id[:8]}...)"
    
    def __str__(self) -> str:
        return f"ChatMessage(id={self.message_id[:8]}...)"


class WhisperChatMessage(AbstractMessage):
    """
    WhisperChatMessageは特定のプレイヤーに送信されるメッセージです。
    送信者ID(sender_id)、受信者ID(recipient_id)、およびメッセージ内容(content)を含みます。
    """
    def __init__(self, sender_id: str, recipient_id: str, content: str):
        super().__init__()
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.content = content

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "content": self.content,
            "message_type": self.message_type,
        })
        return data
    
    def __repr__(self) -> str:
        return f"WhisperChatMessage(id={self.message_id[:8]}...)"
    
    def __str__(self) -> str:
        return f"WhisperChatMessage(id={self.message_id[:8]}...)"


class SystemNotification(AbstractMessage):
    """
    SystemNotificationは特定のプレイヤーに送信されるメッセージです。
    受信者ID(recipient_id)、通知タイプ(notification_type)、および詳細(details)を含みます。
    送信者ID(sender_id)は常に"System"です。
    """
    def __init__(self, recipient_id: str, notification_type: str, details: dict):
        super().__init__()
        self.sender_id = "System"
        self.recipient_id = recipient_id
        self.notification_type = notification_type # "TASK_COMPLETED", "ACHIEVEMENT_UNLOCKED"...
        self.details = details # {"task_name": "...", "reward": 100}...

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "notification_type": self.notification_type,
            "details": self.details,
        })
        return data
    
    def __repr__(self) -> str:
        return f"SystemNotification(id={self.message_id[:8]}...)"
    
    def __str__(self) -> str:
        return f"SystemNotification(id={self.message_id[:8]}...)"


class GameEventMessage(AbstractMessage):
    """
    GameEventMessageは全プレイヤーに送信されるメッセージです。
    イベントタイプ(event_type)、場所(location)、および説明(description)を含みます。
    送信者ID(sender_id)は常に"Environment"です。
    """
    def __init__(self, event_type: str, location_id: str, description: str):
        super().__init__()
        self.sender_id = "Environment"
        self.recipient_id = "Broadcast"
        self.event_type = event_type # "ITEM_SPAWNED", "WEATHER_CHANGED"...
        self.location_id = location_id
        self.description = description

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "location_id": self.location_id,
            "event_type": self.event_type,
            "description": self.description,
        })
        return data
    
    def __repr__(self) -> str:
        return f"GameEventMessage(id={self.message_id[:8]}...)"
    
    def __str__(self) -> str:
        return f"GameEventMessage(id={self.message_id[:8]}...)"


class LocationChatMessage(AbstractMessage):
    """
    LocationChatMessageは同じスポット内でのプレイヤー間会話メッセージです。
    特定のスポットにいるプレイヤー間でのみ送受信されます。
    送信者ID(sender_id)、スポットID(spot_id)、メッセージ内容(content)、および対象プレイヤーID(target_player_id)を含みます。
    target_player_idがNoneの場合は同じスポットの全プレイヤーに送信されます。
    """
    def __init__(self, sender_id: str, spot_id: str, content: str, target_player_id: str = None):
        super().__init__()
        self.sender_id = sender_id
        self.spot_id = spot_id  # メッセージが送信されたスポット
        self.content = content
        self.target_player_id = target_player_id  # Noneの場合は同じスポットの全プレイヤー

    def is_broadcast(self) -> bool:
        """スポット内全体への発言かどうか"""
        return self.target_player_id is None
    
    def is_targeted(self) -> bool:
        """特定のプレイヤーへの発言かどうか"""
        return self.target_player_id is not None
    
    def get_target_player_id(self) -> str:
        """対象プレイヤーIDを取得"""
        return self.target_player_id
    
    def get_spot_id(self) -> str:
        """送信スポットIDを取得"""
        return self.spot_id

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "sender_id": self.sender_id,
            "spot_id": self.spot_id,
            "content": self.content,
            "target_player_id": self.target_player_id,
            "message_type": self.message_type,
        })
        return data
    
    def __repr__(self) -> str:
        return f"LocationChatMessage(id={self.message_id[:8]}...)"
    
    def __str__(self) -> str:
        return f"LocationChatMessage(id={self.message_id[:8]}...)"