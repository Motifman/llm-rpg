from dataclasses import dataclass, field
from datetime import datetime
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.exception import (
    SelfReferenceValidationException,
)


@dataclass(frozen=True)
class BlockRelationShip:
    """ブロック関係性を表現する値オブジェクト"""
    blocker_user_id: UserId
    blocked_user_id: UserId
    created_at: datetime = field(default_factory=datetime.now)

    def __eq__(self, other: object) -> bool:
        """等価性比較（作成時間に関係なく、ブロック実行者とブロック対象のみで判定）"""
        if not isinstance(other, BlockRelationShip):
            return NotImplemented
        return (self.blocker_user_id == other.blocker_user_id and
                self.blocked_user_id == other.blocked_user_id)

    def __hash__(self):
        """ハッシュ値（作成時間に関係なく、ブロック実行者とブロック対象のみで計算）"""
        return hash((int(self.blocker_user_id), int(self.blocked_user_id)))

    def __post_init__(self):
        """ブロック関係性のバリデーション"""
        if self.blocker_user_id == self.blocked_user_id:
            raise SelfReferenceValidationException(int(self.blocker_user_id), "blocker_user_id", "blocked_user_id")

    def is_blocked(self, user_id: UserId) -> bool:
        """指定したユーザーをブロックしているか"""
        return self.blocked_user_id == user_id