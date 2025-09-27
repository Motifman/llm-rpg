from typing import Set, Optional
from src.domain.sns.aggregate.base_sns_aggregate import BaseSnsContentAggregate
from src.domain.sns.value_object import PostContent, Like, Mention, PostId, ReplyId, UserId
from src.domain.sns.event import SnsContentCreatedEvent
from src.domain.sns.exception import InvalidContentTypeException, InvalidParentReferenceException, OwnershipException


class ReplyAggregate(BaseSnsContentAggregate):
    """リプライアグレゲート"""

    def __init__(
        self,
        reply_id: ReplyId,
        parent_post_id: Optional[PostId],
        parent_reply_id: Optional[ReplyId],
        author_user_id: UserId,
        content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        deleted: bool = False,
    ):
        # リプライは必ず親を持つことを保証
        if parent_post_id is None and parent_reply_id is None:
            raise InvalidParentReferenceException("リプライは親ポストまたは親リプライのどちらかを持つ必要があります。")
        if parent_post_id is not None and parent_reply_id is not None:
            raise InvalidParentReferenceException()

        super().__init__(reply_id, author_user_id, content, likes, mentions, deleted, parent_post_id, parent_reply_id)

    @classmethod
    def create_from_db(
        cls,
        reply_id: ReplyId,
        parent_post_id: Optional[PostId],
        parent_reply_id: Optional[ReplyId],
        author_user_id: UserId,
        content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        deleted: bool = False
    ) -> "ReplyAggregate":
        return super().create_from_db(reply_id, author_user_id, content, likes, mentions, deleted, parent_post_id, parent_reply_id)

    @classmethod
    def create(
        cls,
        reply_id: ReplyId,
        parent_post_id: Optional[PostId],
        parent_reply_id: Optional[ReplyId],
        author_user_id: UserId,
        content: PostContent
    ) -> "ReplyAggregate":
        """リプライを作成"""
        mentions = cls._create_mentions_from_content_static(reply_id, content)
        likes = set()
        reply = cls(reply_id, parent_post_id, parent_reply_id, author_user_id, content, likes, mentions)

        # リプライ固有のバリデーション
        if parent_post_id is None and parent_reply_id is None:
            raise InvalidParentReferenceException("リプライは親ポストまたは親リプライのどちらかを持つ必要があります。")
        if parent_post_id is not None and parent_reply_id is not None:
            raise InvalidParentReferenceException()

        # 作成イベントを発行
        event = SnsContentCreatedEvent.create(
            aggregate_id=reply_id,
            aggregate_type="ReplyAggregate",
            target_id=reply_id,
            author_user_id=author_user_id,
            content=content,
            mentions=mentions,
            parent_post_id=parent_post_id,
            parent_reply_id=parent_reply_id,
            content_type="reply"
        )
        reply.add_event(event)

        # メンションイベントを発行
        reply._emit_mentioned_event()

        return reply

    @staticmethod
    def _create_mentions_from_content_static(reply_id: ReplyId, content: PostContent) -> Set[Mention]:
        """コンテンツからメンションを抽出（静的メソッド）"""
        import re
        mention_pattern = r'@(\S+)'
        matches = re.findall(mention_pattern, content.content)
        return set(Mention(mentioned_user_name=match, post_id=reply_id) for match in matches)

    @property
    def reply_id(self) -> ReplyId:
        """リプライID"""
        return self._content_id

    def get_content_type(self) -> str:
        """コンテンツタイプを取得"""
        return "reply"

    def get_parent_info(self) -> tuple[Optional[PostId], Optional[ReplyId]]:
        """親情報を取得"""
        return self._parent_post_id, self._parent_reply_id

    def like_reply(self, user_id: UserId):
        """リプライにいいね"""
        self.like(user_id, "reply")

    def delete_reply(self, user_id: UserId):
        """リプライを削除"""
        self.delete(user_id, "reply")