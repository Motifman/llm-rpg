from dataclasses import dataclass, field
from datetime import datetime
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.exception import (
    SelfReferenceValidationException,
)


@dataclass(frozen=True)
class SubscribeRelationShip:
    """購読関係性を表現する値オブジェクト"""
    subscriber_user_id: UserId
    subscribed_user_id: UserId
    created_at: datetime = field(default_factory=datetime.now)

    def __eq__(self, other: object) -> bool:
        """等価性比較（作成時間に関係なく、購読者と購読対象のみで判定）"""
        if not isinstance(other, SubscribeRelationShip):
            return NotImplemented
        return (self.subscriber_user_id == other.subscriber_user_id and
                self.subscribed_user_id == other.subscribed_user_id)

    def __hash__(self):
        """ハッシュ値（作成時間に関係なく、購読者と購読対象のみで計算）"""
        return hash((int(self.subscriber_user_id), int(self.subscribed_user_id)))

    def __post_init__(self):
        """購読関係性のバリデーション"""
        if self.subscriber_user_id == self.subscribed_user_id:
            raise SelfReferenceValidationException(int(self.subscriber_user_id), "subscriber_user_id", "subscribed_user_id")

    def is_subscribed(self, user_id: UserId) -> bool:
        """指定したユーザーを購読しているか"""
        return self.subscribed_user_id == user_id