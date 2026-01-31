from dataclasses import dataclass, field
from datetime import datetime
from typing import Union
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId


@dataclass(frozen=True)
class Like:
    user_id: UserId
    post_id: Union[PostId, ReplyId]  # ポストIDまたはリプライID
    created_at: datetime = field(default_factory=datetime.now)

    def __eq__(self, other: object) -> bool:
        """等価性比較（作成時間に関係なく、ユーザーIDと投稿IDのみで判定）"""
        if not isinstance(other, Like):
            return NotImplemented
        return (self.user_id == other.user_id and
                self.post_id == other.post_id)

    def __hash__(self):
        """ハッシュ値（作成時間に関係なく、ユーザーIDと投稿IDのみで計算）"""
        # Union型のハッシュ値計算
        post_id_value = int(self.post_id) if hasattr(self.post_id, '__int__') else hash(self.post_id)
        return hash((int(self.user_id), post_id_value))