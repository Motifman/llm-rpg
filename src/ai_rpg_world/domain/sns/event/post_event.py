from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Union

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.sns.value_object import Mention, PostContent, PostId, ReplyId, UserId

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.aggregate import PostAggregate, ReplyAggregate


@dataclass(frozen=True)
class SnsPostCreatedEvent(BaseDomainEvent[PostId, "PostAggregate"]):
    """ポスト作成イベント"""

    post_id: PostId
    author_user_id: UserId
    content: PostContent
    mentions: set[Mention] = field(default_factory=set)
    author_display_name: str = ""
    mentioned_user_ids: frozenset[UserId] = field(default_factory=frozenset)
    subscriber_user_ids: frozenset[UserId] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SnsReplyCreatedEvent(BaseDomainEvent[ReplyId, "ReplyAggregate"]):
    """リプライ作成イベント"""

    reply_id: ReplyId
    author_user_id: UserId
    content: PostContent
    mentions: set[Mention] = field(default_factory=set)
    parent_post_id: PostId | None = None
    parent_reply_id: ReplyId | None = None
    parent_author_id: UserId | None = None  # 親コンテンツの作成者
    author_display_name: str = ""
    mentioned_user_ids: frozenset[UserId] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SnsContentLikedEvent(BaseDomainEvent[Union[PostId, ReplyId], "PostAggregate | ReplyAggregate"]):
    """汎用コンテンツいいねイベント"""

    target_id: PostId | ReplyId
    user_id: UserId  # いいねしたユーザー
    content_author_id: UserId  # コンテンツの作成者
    content_type: str = "post"  # "post" or "reply"
    content_text: str = ""
    liker_display_name: str = ""
    actor_identity_token: str | None = None
    recipient_identity_token: str | None = None
    target_identity_token: str | None = None
    is_liked: bool = True
    execution_provenance: dict[str, object] | None = None


@dataclass(frozen=True)
class SnsContentDeletedEvent(BaseDomainEvent[Union[PostId, ReplyId], "PostAggregate | ReplyAggregate"]):
    """汎用コンテンツ削除イベント"""

    target_id: PostId | ReplyId  # post_id or reply_id
    author_user_id: UserId
    content_type: str = "post"  # "post" or "reply"


@dataclass(frozen=True)
class SnsContentMentionedEvent(BaseDomainEvent[Union[PostId, ReplyId], "PostAggregate | ReplyAggregate"]):
    target_id: PostId | ReplyId
    mentioned_by_user_id: UserId
    mentioned_user_names: set[str]
    content_type: str = "post"  # "post" or "reply"
