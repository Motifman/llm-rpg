from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class FollowRelationShip:
    follower_user_id: int
    followee_user_id: int
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if self.follower_user_id <= 0:
            raise ValueError("follower_user_id must be positive")
        if self.followee_user_id <= 0:
            raise ValueError("followee_user_id must be positive")

    def is_following(self, user_id: int) -> bool:
        """フォローしているか"""
        return self.followee_user_id == user_id