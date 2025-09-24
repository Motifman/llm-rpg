from abc import ABC, abstractmethod
from typing import Optional, Set, TYPE_CHECKING
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.sns.post_content import PostContent
from src.domain.sns.like import Like
from src.domain.sns.mention import Mention
from src.domain.sns.base_sns_event import (
    SnsContentCreatedEvent,
    SnsContentLikedEvent,
    SnsContentDeletedEvent,
    SnsContentMentionedEvent,
    BaseSnsMentionedEvent
)

if TYPE_CHECKING:
    from src.domain.sns.base_sns_event import BaseSnsCreatedEvent, BaseSnsLikedEvent, BaseSnsDeletedEvent


class BaseSnsAggregate(AggregateRoot, ABC):
    """SNSコンテンツアグレゲートの基底クラス"""

    def __init__(
        self,
        content_id: int,
        author_user_id: int,
        content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        deleted: bool = False,
        parent_post_id: Optional[int] = None,
        parent_reply_id: Optional[int] = None,
    ):
        super().__init__()
        self._validate_inputs(content_id, author_user_id)
        self._content_id = content_id
        self._author_user_id = author_user_id
        self._content = content
        self._likes = likes
        self._mentions = mentions
        self._deleted = deleted
        self._parent_post_id = parent_post_id
        self._parent_reply_id = parent_reply_id

    def _validate_inputs(self, content_id: int, author_user_id: int):
        """共通の入力バリデーション"""
        if content_id <= 0:
            raise ValueError(f"content_id must be positive. content_id: {content_id}")
        if author_user_id <= 0:
            raise ValueError(f"author_user_id must be positive. author_user_id: {author_user_id}")

    @classmethod
    def create_from_db(
        cls,
        content_id: int,
        author_user_id: int,
        content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        deleted: bool = False,
        parent_post_id: Optional[int] = None,
        parent_reply_id: Optional[int] = None
    ):
        """データベースからの復元用ファクトリメソッド"""
        return cls(content_id, author_user_id, content, likes, mentions, deleted, parent_post_id, parent_reply_id)

    @property
    def content_id(self) -> int:
        """コンテンツID"""
        return self._content_id

    @property
    def author_user_id(self) -> int:
        """作成者ユーザーID"""
        return self._author_user_id

    @property
    def content(self) -> PostContent:
        """コンテンツ"""
        return self._content

    @property
    def likes(self) -> Set[Like]:
        """いいね一覧"""
        return self._likes.copy()

    @property
    def mentions(self) -> Set[Mention]:
        """メンション一覧"""
        return self._mentions.copy()

    @property
    def deleted(self) -> bool:
        """削除済みかどうか"""
        return self._deleted

    @property
    def parent_post_id(self) -> Optional[int]:
        """親ポストID（リプライの場合）"""
        return self._parent_post_id

    @property
    def parent_reply_id(self) -> Optional[int]:
        """親リプライID（リプライの場合）"""
        return self._parent_reply_id

    def like(self, user_id: int, content_type: str) -> None:
        """いいね機能（共通実装）"""
        like = Like(user_id=user_id)
        if like in self._likes:
            self._likes.remove(like)
        else:
            self._likes.add(like)

        # イベント発行
        event = SnsContentLikedEvent(
            target_id=self._content_id,
            user_id=user_id,
            content_type=content_type,
            content_author_id=self._author_user_id
        )
        self.add_event(event)

    def delete(self, user_id: int, content_type: str) -> None:
        """削除機能（共通実装）"""
        if user_id != self._author_user_id:
            raise ValueError("Cannot delete a content that is not owned by the user")
        self._deleted = True

        # イベント発行
        event = SnsContentDeletedEvent(
            target_id=self._content_id,
            author_user_id=user_id,
            content_type=content_type
        )
        self.add_event(event)

    def get_mentioned_users(self) -> Set[str]:
        """メンションされたユーザー一覧を取得"""
        return set(mention.mentioned_user_name for mention in self._mentions)

    def is_liked_by_user(self, user_id: int) -> bool:
        """指定ユーザーがいいねしているかどうか"""
        return Like(user_id=user_id) in self._likes

    def add_mention(self, mention: Mention) -> None:
        """メンションを追加"""
        self._mentions.add(mention)

    def remove_mention(self, mention: Mention) -> None:
        """メンションを削除"""
        self._mentions.discard(mention)

    @abstractmethod
    def get_content_type(self) -> str:
        """コンテンツタイプを取得（post or reply）"""
        pass

    @abstractmethod
    def get_parent_info(self) -> tuple[Optional[int], Optional[int]]:
        """親情報を取得（parent_post_id, parent_reply_id）"""
        pass

    def _create_mentions_from_content(self, content: PostContent) -> Set[Mention]:
        """コンテンツからメンションを抽出"""
        import re
        mention_pattern = r'@(\S+)'
        matches = re.findall(mention_pattern, content.content)
        return set(Mention(mentioned_user_name=match, post_id=self._content_id) for match in matches)

    def _emit_mentioned_event(self) -> None:
        """メンションイベントを発行"""
        mentioned_users = self.get_mentioned_users()
        if mentioned_users:
            event = BaseSnsMentionedEvent(
                mentioned_user_names=mentioned_users,
                mentioned_by_user_id=self._author_user_id,
                target_id=self._content_id
            )
            self.add_event(event)

