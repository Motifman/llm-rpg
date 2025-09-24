from typing import Set, Optional
from src.domain.sns.base_sns_aggregate import BaseSnsAggregate
from src.domain.sns.post_content import PostContent
from src.domain.sns.like import Like
from src.domain.sns.mention import Mention
from src.domain.sns.base_sns_event import SnsContentCreatedEvent


class ReplyAggregate(BaseSnsAggregate):
    """リプライアグレゲート"""

    def __init__(
        self,
        reply_id: int,
        parent_post_id: Optional[int],
        parent_reply_id: Optional[int],
        author_user_id: int,
        content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        deleted: bool = False,
    ):
        # リプライは必ず親を持つことを保証
        if parent_post_id is None and parent_reply_id is None:
            raise ValueError("Reply must have either parent_post_id or parent_reply_id")
        if parent_post_id is not None and parent_reply_id is not None:
            raise ValueError("Reply cannot have both parent_post_id and parent_reply_id")

        super().__init__(reply_id, author_user_id, content, likes, mentions, deleted, parent_post_id, parent_reply_id)

    @classmethod
    def create_from_db(
        cls,
        reply_id: int,
        parent_post_id: Optional[int],
        parent_reply_id: Optional[int],
        author_user_id: int,
        content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        deleted: bool = False
    ) -> "ReplyAggregate":
        return super().create_from_db(reply_id, author_user_id, content, likes, mentions, deleted, parent_post_id, parent_reply_id)

    @classmethod
    def create(
        cls,
        reply_id: int,
        parent_post_id: Optional[int],
        parent_reply_id: Optional[int],
        author_user_id: int,
        content: PostContent
    ) -> "ReplyAggregate":
        """リプライを作成"""
        mentions = cls._create_mentions_from_content_static(reply_id, content)
        likes = set()
        reply = cls(reply_id, parent_post_id, parent_reply_id, author_user_id, content, likes, mentions)

        # 作成イベントを発行
        event = SnsContentCreatedEvent(
            target_id=reply_id,
            author_user_id=author_user_id,
            content=content.content,
            mentions=mentions,
            content_type="reply",
            parent_post_id=parent_post_id,
            parent_reply_id=parent_reply_id
        )
        reply.add_event(event)

        # メンションイベントを発行
        reply._emit_mentioned_event()

        return reply

    @staticmethod
    def _create_mentions_from_content_static(reply_id: int, content: PostContent) -> Set[Mention]:
        """コンテンツからメンションを抽出（静的メソッド）"""
        import re
        mention_pattern = r'@(\S+)'
        matches = re.findall(mention_pattern, content.content)
        return set(Mention(mentioned_user_name=match, post_id=reply_id) for match in matches)

    @property
    def reply_id(self) -> int:
        """リプライID"""
        return self._content_id

    def get_content_type(self) -> str:
        """コンテンツタイプを取得"""
        return "reply"

    def get_parent_info(self) -> tuple[Optional[int], Optional[int]]:
        """親情報を取得"""
        return self._parent_post_id, self._parent_reply_id

    def like_reply(self, user_id: int):
        """リプライにいいね"""
        self.like(user_id, "reply")

    def delete_reply(self, user_id: int):
        """リプライを削除"""
        self.delete(user_id, "reply")