from enum import Enum


class NotificationType(Enum):
    """通知タイプ"""
    FOLLOW = "follow"
    MENTION = "mention"
    LIKE = "like"
    REPLY = "reply"
    SUBSCRIBE = "subscribe"
    POST = "post"

    def __str__(self) -> str:
        return self.value
