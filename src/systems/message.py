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
    ChatMessage is a message that is sent to all agents in the same location.
    It contains the sender_id and content.
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
    WhisperChatMessage is a message that is sent between two agents.
    It contains the sender_id, recipient_id, and content.
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
    SystemNotification is a message that is sent to an agent.
    It contains the recipient_id, notification_type, and details.
    The sender_id is always "System".
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
    GameEventMessage is a message that is sent to all agents.
    It contains the event_type, location, and description.
    The sender_id is always "Environment".
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