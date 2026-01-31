from abc import ABC, abstractmethod
from typing import Optional, Set, Union
from datetime import datetime
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.sns.value_object import PostContent, Like, Mention, PostId, ReplyId, UserId
from ai_rpg_world.domain.sns.event import SnsContentLikedEvent, SnsContentDeletedEvent, SnsContentMentionedEvent
from ai_rpg_world.domain.sns.exception import InvalidContentTypeException, OwnershipException, ContentTypeException, ContentAlreadyDeletedException


class BaseSnsContentAggregate(AggregateRoot, ABC):
    """SNSコンテンツアグレゲートの基底クラス"""

    def __init__(
        self,
        content_id: Union[PostId, ReplyId],
        author_user_id: UserId,
        content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        deleted: bool = False,
        parent_post_id: Optional[PostId] = None,
        parent_reply_id: Optional[ReplyId] = None,
        created_at: Optional[datetime] = None,
    ):
        super().__init__()
        self._content_id = content_id
        self._author_user_id = author_user_id
        self._content = content
        self._likes = likes
        self._mentions = mentions
        self._deleted = deleted
        self._parent_post_id = parent_post_id
        self._parent_reply_id = parent_reply_id
        self._created_at = created_at if created_at is not None else datetime.now()

    @classmethod
    def create_from_db(
        cls,
        content_id: Union[PostId, ReplyId],
        author_user_id: UserId,
        content: PostContent,
        likes: Set[Like],
        mentions: Set[Mention],
        reply_ids: Set[ReplyId] = None,  # PostAggregate用（ReplyAggregateでは無視）
        deleted: bool = False,
        parent_post_id: Optional[PostId] = None,
        parent_reply_id: Optional[ReplyId] = None,
        created_at: Optional[datetime] = None
    ):
        """データベースからの復元用ファクトリメソッド"""
        # 全てのケースでcreated_atを渡す
        # reply_idsがNoneの場合は空のセットを使用（ReplyAggregate用）
        if reply_ids is None:
            reply_ids = set()
        return cls(content_id, author_user_id, content, likes, mentions, reply_ids, deleted, parent_post_id, parent_reply_id, created_at)

    @property
    def content_id(self) -> Union[PostId, ReplyId]:
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
    def parent_post_id(self) -> Optional[PostId]:
        """親ポストID（リプライの場合）"""
        return self._parent_post_id

    @property
    def parent_reply_id(self) -> Optional[ReplyId]:
        """親リプライID（リプライの場合）"""
        return self._parent_reply_id

    @property
    def created_at(self) -> datetime:
        """作成日時"""
        return self._created_at

    def like(self, user_id: UserId, content_type: str) -> None:
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
            content_author_id=self._author_user_id
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

    def get_mentioned_users(self) -> Set[str]:
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
    def get_parent_info(self) -> tuple[Optional[int], Optional[int]]:
        """親情報を取得（parent_post_id, parent_reply_id）"""
        pass

    @abstractmethod
    def get_display_info(self, viewer_user_id: UserId) -> dict:
        """表示用の情報をまとめて取得"""
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
