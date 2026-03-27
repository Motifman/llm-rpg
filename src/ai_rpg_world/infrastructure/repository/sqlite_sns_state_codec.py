"""Helpers for reconstructing SNS aggregates from normalized SQLite rows."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence, Set

from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.entity.sns_user import SnsUser
from ai_rpg_world.domain.sns.enum.sns_enum import PostVisibility
from ai_rpg_world.domain.sns.value_object.block import BlockRelationShip
from ai_rpg_world.domain.sns.value_object.follow import FollowRelationShip
from ai_rpg_world.domain.sns.value_object.like import Like
from ai_rpg_world.domain.sns.value_object.mention import Mention
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.post_content import PostContent
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.value_object.subscribe import SubscribeRelationShip
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.value_object.user_profile import UserProfile


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def build_user_aggregate(
    *,
    user_id: int,
    user_name: str,
    display_name: str,
    bio: str,
    follows: Sequence[tuple[int, int, str]],
    blocks: Sequence[tuple[int, int, str]],
    subscriptions: Sequence[tuple[int, int, str]],
) -> UserAggregate:
    return UserAggregate(
        user_id=UserId(user_id),
        sns_user=SnsUser(
            UserId(user_id),
            UserProfile(user_name=user_name, display_name=display_name, bio=bio),
        ),
        follow_relationships=[
            FollowRelationShip(
                follower_user_id=UserId(follower_user_id),
                followee_user_id=UserId(followee_user_id),
                created_at=_parse_dt(created_at),
            )
            for follower_user_id, followee_user_id, created_at in follows
        ],
        block_relationships=[
            BlockRelationShip(
                blocker_user_id=UserId(blocker_user_id),
                blocked_user_id=UserId(blocked_user_id),
                created_at=_parse_dt(created_at),
            )
            for blocker_user_id, blocked_user_id, created_at in blocks
        ],
        subscribe_relationships=[
            SubscribeRelationShip(
                subscriber_user_id=UserId(subscriber_user_id),
                subscribed_user_id=UserId(subscribed_user_id),
                created_at=_parse_dt(created_at),
            )
            for subscriber_user_id, subscribed_user_id, created_at in subscriptions
        ],
    )


def build_post_aggregate(
    *,
    post_id: int,
    author_user_id: int,
    content: str,
    visibility: str,
    deleted: int,
    created_at: str,
    hashtags: Iterable[str],
    likes: Sequence[tuple[int, str]],
    mentions: Iterable[str],
    reply_ids: Iterable[int],
) -> PostAggregate:
    post_id_vo = PostId(post_id)
    return PostAggregate.create_from_db(
        post_id=post_id_vo,
        author_user_id=UserId(author_user_id),
        post_content=PostContent(
            content=content,
            hashtags=tuple(hashtags),
            visibility=PostVisibility(visibility),
        ),
        likes={
            Like(user_id=UserId(user_id), post_id=post_id_vo, created_at=_parse_dt(created))
            for user_id, created in likes
        },
        mentions={Mention(mentioned_user_name=name, post_id=post_id_vo) for name in mentions},
        reply_ids={ReplyId(reply_id) for reply_id in reply_ids},
        deleted=bool(deleted),
        created_at=_parse_dt(created_at),
    )


def build_reply_aggregate(
    *,
    reply_id: int,
    author_user_id: int,
    parent_post_id: int | None,
    parent_reply_id: int | None,
    content: str,
    visibility: str,
    deleted: int,
    created_at: str,
    hashtags: Iterable[str],
    likes: Sequence[tuple[int, str]],
    mentions: Iterable[str],
    child_reply_ids: Iterable[int],
) -> ReplyAggregate:
    reply_id_vo = ReplyId(reply_id)
    return ReplyAggregate.create_from_db(
        reply_id=reply_id_vo,
        parent_post_id=None if parent_post_id is None else PostId(parent_post_id),
        parent_reply_id=None if parent_reply_id is None else ReplyId(parent_reply_id),
        author_user_id=UserId(author_user_id),
        content=PostContent(
            content=content,
            hashtags=tuple(hashtags),
            visibility=PostVisibility(visibility),
        ),
        likes={
            Like(user_id=UserId(user_id), post_id=reply_id_vo, created_at=_parse_dt(created))
            for user_id, created in likes
        },
        mentions={Mention(mentioned_user_name=name, post_id=reply_id_vo) for name in mentions},
        reply_ids={ReplyId(child_reply_id) for child_reply_id in child_reply_ids},
        deleted=bool(deleted),
        created_at=_parse_dt(created_at),
    )


def build_notification(row: tuple) -> Notification:
    (
        notification_id,
        user_id,
        notification_type,
        title,
        message,
        actor_user_id,
        actor_user_name,
        related_post_id,
        related_reply_id,
        content_type,
        content_text,
        created_at,
        is_read,
        expires_at,
    ) = row
    return Notification(
        notification_id=NotificationId(notification_id),
        user_id=UserId(user_id),
        notification_type=NotificationType(notification_type),
        content=NotificationContent(
            title=title,
            message=message,
            actor_user_id=UserId(actor_user_id),
            actor_user_name=actor_user_name,
            related_post_id=None if related_post_id is None else PostId(related_post_id),
            related_reply_id=None if related_reply_id is None else ReplyId(related_reply_id),
            content_type=content_type,
            content_text=content_text,
        ),
        created_at=_parse_dt(created_at),
        is_read=bool(is_read),
        expires_at=None if expires_at is None else _parse_dt(expires_at),
    )


__all__ = [
    "build_notification",
    "build_post_aggregate",
    "build_reply_aggregate",
    "build_user_aggregate",
]
