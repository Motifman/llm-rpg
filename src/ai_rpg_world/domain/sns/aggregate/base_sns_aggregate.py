from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Generic, TypeVar, Union

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.sns.event import SnsContentDeletedEvent, SnsContentLikedEvent, SnsContentMentionedEvent
from ai_rpg_world.domain.sns.exception import (
    ContentAlreadyDeletedException,
    ContentTypeException,
    InvalidContentTypeException,
    OwnershipException,
)
from ai_rpg_world.domain.sns.value_object import Like, Mention, PostContent, PostId, ReplyId, UserId
from ai_rpg_world.domain.sns.value_object.sns_identity_token import SnsIdentityToken

ContentId = TypeVar("ContentId", PostId, ReplyId)


class BaseSnsContentAggregate(AggregateRoot, ABC, Generic[ContentId]):
    """SNSコンテンツアグレゲートの基底クラス"""

    def __init__(
        self,
        content_id: ContentId,
        author_user_id: UserId,
        content: PostContent,
        likes: set[Like],
        mentions: set[Mention],
        deleted: bool = False,
        parent_post_id: PostId | None = None,
        parent_reply_id: ReplyId | None = None,
        created_at: datetime | None = None,
        identity_token: str | None = None,
        author_identity_token: str | None = None,
        parent_identity_token: str | None = None,
    ):
        super().__init__()
        self._content_id: ContentId = content_id
        self._author_user_id = author_user_id
        self._content = content
        self._likes = likes
        self._mentions = mentions
        self._deleted = deleted
        self._parent_post_id = parent_post_id
        self._parent_reply_id = parent_reply_id
        self._created_at = created_at if created_at is not None else datetime.now()
        self._identity_token = SnsIdentityToken() if identity_token is None else SnsIdentityToken(identity_token)
        self._author_identity_token = None if author_identity_token is None else SnsIdentityToken(author_identity_token).value
        self._parent_identity_token = None if parent_identity_token is None else SnsIdentityToken(parent_identity_token).value

    @property
    def identity_token(self) -> str:
        """整数の採番や表示順序と独立した、作成時から変わらない識別子。"""
        return self._identity_token.value

    @property
    def author_identity_token(self) -> str | None:
        """作成時の作者の識別子。欠損時に現在の同じ整数の利用者へ結び直さない。"""
        return self._author_identity_token

    @property
    def parent_identity_token(self) -> str | None:
        """作成時の親の識別子。返信以外、または旧形式の欠損時は None。"""
        return self._parent_identity_token

    @property
    def content_id(self) -> ContentId:
        """コンテンツID"""
        return self._content_id

    @property
    def author_user_id(self) -> UserId:
        """作成者ユーザーID"""
        return self._author_user_id

    @property
    def content(self) -> PostContent:
        """コンテンツ"""
        return self._content

    @property
    def likes(self) -> set[Like]:
        """いいね一覧"""
        return self._likes.copy()

    @property
    def mentions(self) -> set[Mention]:
        """メンション一覧"""
        return self._mentions.copy()

    @property
    def deleted(self) -> bool:
        """削除済みかどうか"""
        return self._deleted

    @property
    def parent_post_id(self) -> PostId | None:
        """親ポストID（リプライの場合）"""
        return self._parent_post_id

    @property
    def parent_reply_id(self) -> ReplyId | None:
        """親リプライID（リプライの場合）"""
        return self._parent_reply_id

    @property
    def created_at(self) -> datetime:
        """作成日時"""
        return self._created_at

    def like(self, user_id: UserId, content_type: str, *, liker_display_name: str = "", liker_identity_token: str | None = None, execution_provenance: dict[str, object] | None = None) -> None:
        """いいね機能（共通実装）"""
        # コンテンツタイプのバリデーション
        if content_type not in ["post", "reply"]:
            raise InvalidContentTypeException(content_type)

        # Likeオブジェクトを作成（PostIdまたはReplyIdの両方をサポート）
        like = Like(user_id=user_id, post_id=self._content_id)
        if like in self._likes:
            self._likes.remove(like)
        else:
            self._likes.add(like)

        # イベント発行
        aggregate_type = "PostAggregate" if self.get_content_type() == "post" else "ReplyAggregate"
        event = SnsContentLikedEvent.create(
            aggregate_id=self._content_id,
            aggregate_type=aggregate_type,
            target_id=self._content_id,
            user_id=user_id,
            content_type=content_type,
            content_author_id=self._author_user_id,
            content_text=self._content.content,
            liker_display_name=liker_display_name,
            actor_identity_token=liker_identity_token,
            recipient_identity_token=self._author_identity_token,
            target_identity_token=self.identity_token,
            is_liked=like in self._likes,
            execution_provenance=execution_provenance,
        )
        self.add_event(event)

    def delete(self, user_id: UserId, content_type: str) -> None:
        """削除機能（共通実装）"""
        # コンテンツタイプのバリデーション
        if content_type not in ["post", "reply"]:
            raise InvalidContentTypeException(content_type)

        if user_id != self._author_user_id:
            raise OwnershipException(user_id.value, self._content_id.value, content_type)

        # すでに削除済みかどうかのチェック
        if self._deleted:
            raise ContentAlreadyDeletedException(self._content_id.value, content_type)

        self._deleted = True

        # イベント発行
        aggregate_type = "PostAggregate" if self.get_content_type() == "post" else "ReplyAggregate"
        event = SnsContentDeletedEvent.create(
            aggregate_id=self._content_id,
            aggregate_type=aggregate_type,
            target_id=self._content_id,
            author_user_id=user_id,
            content_type=content_type
        )
        self.add_event(event)

    def get_mentioned_users(self) -> set[str]:
        """メンションされたユーザー一覧を取得"""
        return set(mention.mentioned_user_name for mention in self._mentions)

    def is_liked_by_user(self, user_id: UserId) -> bool:
        """指定ユーザーがいいねしているかどうか"""
        # Likeオブジェクトを作成してチェック
        like = Like(user_id=user_id, post_id=self._content_id)
        return like in self._likes

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
    def get_parent_info(self) -> tuple[PostId | None, ReplyId | None]:
        """親情報を取得（parent_post_id, parent_reply_id）"""
        pass

    @abstractmethod
    def get_display_info(self, viewer_user_id: UserId) -> dict[str, Any]:
        """表示用の情報をまとめて取得"""
        pass

    def _create_mentions_from_content(self, content: PostContent) -> set[Mention]:
        """コンテンツからメンションを抽出"""
        import re
        mention_pattern = r'@(\S+)'
        matches = re.findall(mention_pattern, content.content)
        return set(Mention(mentioned_user_name=match, post_id=self._content_id) for match in matches)

    def _emit_mentioned_event(self) -> None:
        """メンションイベントを発行"""
        mentioned_users = self.get_mentioned_users()
        if mentioned_users:
            content_type = self.get_content_type()
            # コンテンツタイプのバリデーション
            if content_type not in ["post", "reply"]:
                raise InvalidContentTypeException(content_type)

            aggregate_type = "PostAggregate" if content_type == "post" else "ReplyAggregate"
            event = SnsContentMentionedEvent.create(
                aggregate_id=self._content_id,
                aggregate_type=aggregate_type,
                target_id=self._content_id,
                mentioned_by_user_id=self._author_user_id,
            mentioned_user_names=mentioned_users,
            content_type=content_type
            )
            self.add_event(event)
