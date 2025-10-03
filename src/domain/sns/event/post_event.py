from dataclasses import dataclass, field
from src.domain.sns.value_object import PostContent, Mention, UserId, PostId, ReplyId
from src.domain.common.domain_event import BaseDomainEvent
from typing import Set, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.sns.aggregate import PostAggregate, ReplyAggregate


@dataclass(frozen=True)
class SnsPostCreatedEvent(BaseDomainEvent[PostId, "PostAggregate"]):
    """ポスト作成イベント"""
    post_id: PostId
    author_user_id: UserId
    content: PostContent
    mentions: Set[Mention] = field(default_factory=set)


@dataclass(frozen=True)
class SnsReplyCreatedEvent(BaseDomainEvent[ReplyId, "ReplyAggregate"]):
    """リプライ作成イベント"""
    reply_id: ReplyId
    author_user_id: UserId
    content: PostContent
    mentions: Set[Mention] = field(default_factory=set)
    parent_post_id: Optional[PostId] = None
    parent_reply_id: Optional[ReplyId] = None
    parent_author_id: Optional[UserId] = None  # 親コンテンツの作成者


@dataclass(frozen=True)
class SnsContentLikedEvent(BaseDomainEvent[Union[PostId, ReplyId], "PostAggregate | ReplyAggregate"]):
    """汎用コンテンツいいねイベント"""
    target_id: Union[PostId, ReplyId]
    user_id: UserId      # いいねしたユーザー
    content_author_id: UserId  # コンテンツの作成者
    content_type: str = "post"  # "post" or "reply"


@dataclass(frozen=True)
class SnsContentDeletedEvent(BaseDomainEvent[Union[PostId, ReplyId], "PostAggregate | ReplyAggregate"]):
    """汎用コンテンツ削除イベント"""
    target_id: Union[PostId, ReplyId]  # post_id or reply_id
    author_user_id: UserId
    content_type: str = "post"  # "post" or "reply"


@dataclass(frozen=True)
class SnsContentMentionedEvent(BaseDomainEvent[Union[PostId, ReplyId], "PostAggregate | ReplyAggregate"]):
    target_id: Union[PostId, ReplyId]
    mentioned_by_user_id: UserId
    mentioned_user_names: Set[str]
    content_type: str = "post"  # "post" or "reply"