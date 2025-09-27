from typing import Set, Optional
from src.domain.sns.aggregate.base_sns_aggregate import BaseSnsContentAggregate
from src.domain.sns.value_object import Like, PostContent, Mention, PostId, ReplyId, UserId
from src.domain.sns.event import SnsContentCreatedEvent
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
        deleted: bool = False,
        parent_post_id: Optional[PostId] = None,
        parent_reply_id: Optional[ReplyId] = None,
    ):
        # ポストは親を持つことができない
        if parent_post_id is not None or parent_reply_id is not None:
            raise InvalidParentReferenceException("ポストは親ポストまたは親リプライを持つことはできません。")

        super().__init__(post_id, author_user_id, post_content, likes, mentions, deleted, parent_post_id, parent_reply_id)

    @classmethod
    def create_from_db(
        cls,
        post_id: PostId,
        author_user_id: UserId,
        post_content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        deleted: bool = False
    ) -> "PostAggregate":
        return super().create_from_db(post_id, author_user_id, post_content, likes, mentions, deleted)

    @classmethod
    def create(cls, post_id: PostId, author_user_id: UserId, post_content: PostContent) -> "PostAggregate":
        """投稿を作成"""
        mentions = cls._create_mentions_from_content_static(post_id, post_content)
        likes = set()
        post = cls(post_id, author_user_id, post_content, likes, mentions)

        # ポスト固有のバリデーション
        if post._parent_post_id is not None or post._parent_reply_id is not None:
            raise InvalidParentReferenceException()

        # 作成イベントを発行
        event = SnsContentCreatedEvent.create(
            aggregate_id=post_id,
            aggregate_type="PostAggregate",
            target_id=post_id,
            author_user_id=author_user_id,
            content=post_content,
            mentions=mentions,
            parent_post_id=None,
            parent_reply_id=None,
            content_type="post"
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