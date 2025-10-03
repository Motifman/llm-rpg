from typing import Set, Optional
from datetime import datetime
from src.domain.sns.aggregate.base_sns_aggregate import BaseSnsContentAggregate
from src.domain.sns.value_object import Like, PostContent, Mention, PostId, ReplyId, UserId
from src.domain.sns.event import SnsPostCreatedEvent
from src.domain.sns.exception import InvalidContentTypeException, InvalidParentReferenceException, OwnershipException


class PostAggregate(BaseSnsContentAggregate):
    """ポスト集約"""

    def __init__(
        self,
        post_id: PostId,
        author_user_id: UserId,
        post_content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        reply_ids: Set[ReplyId],  # リプライIDの一覧
        deleted: bool = False,
        parent_post_id: Optional[PostId] = None,
        parent_reply_id: Optional[ReplyId] = None,
        created_at: Optional[datetime] = None,
    ):
        # ポストは親を持つことができない
        if parent_post_id is not None or parent_reply_id is not None:
            raise InvalidParentReferenceException("ポストは親ポストまたは親リプライを持つことはできません。")

        super().__init__(post_id, author_user_id, post_content, likes, mentions, deleted, parent_post_id, parent_reply_id, created_at)
        self._reply_ids = reply_ids.copy()

    @classmethod
    def create_from_db(
        cls,
        post_id: PostId,
        author_user_id: UserId,
        post_content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        reply_ids: Set[ReplyId],  # リプライIDの一覧
        deleted: bool = False,
        created_at: Optional[datetime] = None
    ) -> "PostAggregate":
        return super().create_from_db(post_id, author_user_id, post_content, likes, mentions, reply_ids, deleted, None, None, created_at)

    @classmethod
    def create(cls, post_id: PostId, author_user_id: UserId, post_content: PostContent) -> "PostAggregate":
        """投稿を作成"""
        mentions = cls._create_mentions_from_content_static(post_id, post_content)
        likes = set()
        reply_ids = set()  # 新しいポストなのでリプライは空
        post = cls(post_id, author_user_id, post_content, likes, mentions, reply_ids)

        # ポスト固有のバリデーション
        if post._parent_post_id is not None or post._parent_reply_id is not None:
            raise InvalidParentReferenceException()

        # 作成イベントを発行
        event = SnsPostCreatedEvent.create(
            aggregate_id=post_id,
            aggregate_type="PostAggregate",
            post_id=post_id,
            author_user_id=author_user_id,
            content=post_content,
            mentions=mentions
        )
        post.add_event(event)

        # メンションイベントを発行
        post._emit_mentioned_event()

        return post

    @staticmethod
    def _create_mentions_from_content_static(post_id: PostId, post_content: PostContent) -> Set[Mention]:
        """コンテンツからメンションを抽出（静的メソッド）"""
        import re
        mention_pattern = r'@(\S+)'
        matches = re.findall(mention_pattern, post_content.content)
        return set(Mention(mentioned_user_name=match, post_id=post_id) for match in matches)

    @property
    def post_id(self) -> PostId:
        """ポストID"""
        return self._content_id

    @property
    def post_content(self) -> PostContent:
        """ポストコンテンツ"""
        return self._content

    def get_content_type(self) -> str:
        """コンテンツタイプを取得"""
        return "post"

    def get_parent_info(self) -> tuple[Optional[PostId], Optional[ReplyId]]:
        """親情報を取得"""
        return None, None

    def like_post(self, user_id: UserId):
        """ポストにいいね"""
        self.like(user_id, "post")

    def delete_post(self, user_id: UserId):
        """ポストを削除"""
        self.delete(user_id, "post")

    def mentioned_users(self) -> Set[str]:
        """メンションされたユーザー一覧を取得"""
        return self.get_mentioned_users()

    @property
    def reply_ids(self) -> Set[ReplyId]:
        """リプライIDの一覧を取得"""
        return self._reply_ids.copy()

    def get_reply_count(self) -> int:
        """リプライ数を取得"""
        return len(self._reply_ids)

    def get_like_count(self) -> int:
        """いいね数を取得"""
        return len(self.likes)

    def add_reply(self, reply_id: ReplyId) -> None:
        """リプライを追加"""
        self._reply_ids.add(reply_id)

    def remove_reply(self, reply_id: ReplyId) -> None:
        """リプライを削除"""
        self._reply_ids.discard(reply_id)

    def is_private(self) -> bool:
        """ポストがプライベートかどうかを判定"""
        from src.domain.sns.enum.sns_enum import PostVisibility
        return self.post_content.visibility == PostVisibility.PRIVATE

    def get_sort_key_by_created_at(self) -> datetime:
        """ソート用の作成日時を取得"""
        return self.created_at

    def get_display_info(self, viewer_user_id: UserId) -> dict:
        """表示用の情報をまとめて取得"""
        return {
            "post_id": self.post_id.value,
            "author_user_id": self.author_user_id.value,
            "content": self.post_content.content,
            "hashtags": list(self.post_content.hashtags),
            "visibility": self.post_content.visibility.value,
            "created_at": self.created_at,
            "like_count": self.get_like_count(),
            "reply_count": self.get_reply_count(),
            "is_liked_by_viewer": self.is_liked_by_user(viewer_user_id),
            "is_replied_by_viewer": False,  # ポストには直接リプライできない
            "mentioned_users": list(self.mentioned_users()),
            "is_deleted": self.deleted
        }