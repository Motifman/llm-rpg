from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SubscribeRelationShip:
    subscriber_user_id: int
    subscribed_user_id: int
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if self.subscriber_user_id <= 0:
            raise ValueError("subscriber_user_id must be positive")
        if self.subscribed_user_id <= 0:
            raise ValueError("subscribed_user_id must be positive")

    def is_subscribed(self, user_id: int) -> bool:
        return self.subscribed_user_id == user_id