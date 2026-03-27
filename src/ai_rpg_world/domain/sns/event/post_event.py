from dataclasses import dataclass, field
from ai_rpg_world.domain.sns.value_object import PostContent, Mention, UserId, PostId, ReplyId
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from typing import FrozenSet, Set, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.aggregate import PostAggregate, ReplyAggregate


@dataclass(frozen=True)
class SnsPostCreatedEvent(BaseDomainEvent[PostId, "PostAggregate"]):
    """ポスト作成イベント"""
    post_id: PostId
    author_user_id: UserId
    content: PostContent
    mentions: Set[Mention] = field(default_factory=set)
    author_display_name: str = ""
    mentioned_user_ids: FrozenSet[UserId] = field(default_factory=frozenset)
    subscriber_user_ids: FrozenSet[UserId] = field(default_factory=frozenset)


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
    author_display_name: str = ""
    mentioned_user_ids: FrozenSet[UserId] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SnsContentLikedEvent(BaseDomainEvent[Union[PostId, ReplyId], "PostAggregate | ReplyAggregate"]):
    """汎用コンテンツいいねイベント"""
    target_id: Union[PostId, ReplyId]
    user_id: UserId      # いいねしたユーザー
    content_author_id: UserId  # コンテンツの作成者
    content_type: str = "post"  # "post" or "reply"
    content_text: str = ""
    liker_display_name: str = ""


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