from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class BlockRelationShip:
    blocker_user_id: int
    blocked_user_id: int
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if self.blocker_user_id <= 0:
            raise ValueError("blocker_user_id must be positive")
        if self.blocked_user_id <= 0:
            raise ValueError("blocked_user_id must be positive")

    def is_blocked(self, user_id: int) -> bool:
        return self.blocked_user_id == user_id