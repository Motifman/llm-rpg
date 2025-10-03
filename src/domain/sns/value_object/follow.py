from dataclasses import dataclass, field
from datetime import datetime
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.exception import (
    SelfReferenceValidationException,
)


@dataclass(frozen=True)
class FollowRelationShip:
    """フォロー関係性を表現する値オブジェクト"""
    follower_user_id: UserId
    followee_user_id: UserId
    created_at: datetime = field(default_factory=datetime.now)

    def __eq__(self, other: object) -> bool:
        """等価性比較（作成時間に関係なく、フォロワーとフォロー対象のみで判定）"""
        if not isinstance(other, FollowRelationShip):
            return NotImplemented
        return (self.follower_user_id == other.follower_user_id and
                self.followee_user_id == other.followee_user_id)

    def __hash__(self):
        """ハッシュ値（作成時間に関係なく、フォロワーとフォロー対象のみで計算）"""
        return hash((int(self.follower_user_id), int(self.followee_user_id)))

    def __post_init__(self):
        """フォロー関係性のバリデーション"""
        if self.follower_user_id == self.followee_user_id:
            raise SelfReferenceValidationException(int(self.follower_user_id), "follower_user_id", "followee_user_id")

    def is_following(self, user_id: UserId) -> bool:
        """指定したユーザーをフォローしているか"""
        return self.followee_user_id == user_id