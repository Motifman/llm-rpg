from datetime import datetime
from typing import Any

from ai_rpg_world.domain.sns.aggregate.base_sns_aggregate import BaseSnsContentAggregate
from ai_rpg_world.domain.sns.event import SnsReplyCreatedEvent
from ai_rpg_world.domain.sns.exception import (
    InvalidContentTypeException,
    InvalidParentReferenceException,
    OwnershipException,
)
from ai_rpg_world.domain.sns.value_object import Like, Mention, PostContent, PostId, ReplyId, UserId


class ReplyAggregate(BaseSnsContentAggregate[ReplyId]):
    """リプライアグレゲート"""

    def __init__(
        self,
        reply_id: ReplyId,
        author_user_id: UserId,
        content: PostContent,
        likes: set[Like],
        mentions: set[Mention],
        reply_ids: set[ReplyId],  # 子リプライIDの一覧
        deleted: bool = False,
        parent_post_id: PostId | None = None,
        parent_reply_id: ReplyId | None = None,
        created_at: datetime | None = None,
        identity_token: str | None = None,
        author_identity_token: str | None = None,
        parent_identity_token: str | None = None,
    ):
        # リプライは必ず親を持つことを保証
        if parent_post_id is None and parent_reply_id is None:
            raise InvalidParentReferenceException("リプライは親ポストまたは親リプライのどちらかを持つ必要があります。")
        if parent_post_id is not None and parent_reply_id is not None:
            raise InvalidParentReferenceException("親ポストIDと親リプライIDを同時に設定することはできません。")

        super().__init__(reply_id, author_user_id, content, likes, mentions, deleted, parent_post_id, parent_reply_id, created_at, identity_token, author_identity_token, parent_identity_token)
        self._reply_ids = reply_ids.copy()

    @classmethod
    def create_from_db(
        cls,
        reply_id: ReplyId,
        parent_post_id: PostId | None,
        parent_reply_id: ReplyId | None,
        author_user_id: UserId,
        content: PostContent,
        likes: set[Like],
        mentions: set[Mention],
        reply_ids: set[ReplyId],  # 子リプライIDの一覧
        deleted: bool = False,
        created_at: datetime | None = None,
        identity_token: str | None = None,
        author_identity_token: str | None = None,
        parent_identity_token: str | None = None,
    ) -> "ReplyAggregate":
        return cls(reply_id, author_user_id, content, likes, mentions, reply_ids, deleted, parent_post_id, parent_reply_id, created_at, identity_token, author_identity_token, parent_identity_token)

    @classmethod
    def create(
        cls,
        reply_id: ReplyId,
        parent_post_id: PostId | None,
        parent_reply_id: ReplyId | None,
        parent_author_id: UserId | None,
        author_user_id: UserId,
        content: PostContent,
        *,
        author_display_name: str = "",
        mentioned_user_ids: frozenset[UserId] = frozenset(),
        author_identity_token: str | None = None,
        parent_identity_token: str | None = None,
    ) -> "ReplyAggregate":
        """リプライを作成"""
        mentions = cls._create_mentions_from_content_static(reply_id, content)
        likes: set[Like] = set()
        reply_ids: set[ReplyId] = set()  # 新しいリプライなので子リプライは空
        reply = cls(reply_id, author_user_id, content, likes, mentions, reply_ids, deleted=False, parent_post_id=parent_post_id, parent_reply_id=parent_reply_id, author_identity_token=author_identity_token, parent_identity_token=parent_identity_token)

        # 作成イベントを発行
        event = SnsReplyCreatedEvent.create(
            aggregate_id=reply_id,
            aggregate_type="ReplyAggregate",
            reply_id=reply_id,
            author_user_id=author_user_id,
            content=content,
            mentions=mentions,
            parent_post_id=parent_post_id,
            parent_reply_id=parent_reply_id,
            parent_author_id=parent_author_id,
            author_display_name=author_display_name,
            mentioned_user_ids=mentioned_user_ids,
        )
        reply.add_event(event)

        # メンションイベントを発行
        reply._emit_mentioned_event()

        return reply

    @staticmethod
    def _create_mentions_from_content_static(reply_id: ReplyId, content: PostContent) -> set[Mention]:
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

    def get_parent_info(self) -> tuple[PostId | None, ReplyId | None]:
        """親情報を取得"""
        return self._parent_post_id, self._parent_reply_id

    def like_reply(self, user_id: UserId, liker_display_name: str = "", *, liker_identity_token: str | None = None, execution_provenance: dict[str, object] | None = None) -> None:
        """リプライにいいね"""
        self.like(user_id, "reply", liker_display_name=liker_display_name, liker_identity_token=liker_identity_token, execution_provenance=execution_provenance)

    def delete_reply(self, user_id: UserId) -> None:
        """リプライを削除"""
        self.delete(user_id, "reply")

    @property
    def reply_ids(self) -> set[ReplyId]:
        """子リプライIDの一覧を取得"""
        return self._reply_ids.copy()

    def get_reply_count(self) -> int:
        """子リプライ数を取得"""
        return len(self._reply_ids)

    def add_reply(self, reply_id: ReplyId) -> None:
        """子リプライを追加"""
        self._reply_ids.add(reply_id)

    def remove_reply(self, reply_id: ReplyId) -> None:
        """子リプライを削除"""
        self._reply_ids.discard(reply_id)

    def get_display_info(self, viewer_user_id: UserId) -> dict[str, Any]:
        """表示用の情報をまとめて取得"""
        return {
            "reply_id": self.reply_id.value,
            "parent_post_id": self.parent_post_id.value if self.parent_post_id else None,
            "parent_reply_id": self.parent_reply_id.value if self.parent_reply_id else None,
            "author_user_id": self.author_user_id.value,
            "content": self.content.content,
            "hashtags": list(self.content.hashtags),
            "visibility": self.content.visibility.value,
            "created_at": self.created_at,
            "like_count": len(self.likes),
            "reply_count": self.get_reply_count(),
            "is_liked_by_viewer": self.is_liked_by_user(viewer_user_id),
            "mentioned_users": list(self.get_mentioned_users()),
            "is_deleted": self.deleted,
            "has_replies": self.get_reply_count() > 0,
        }
