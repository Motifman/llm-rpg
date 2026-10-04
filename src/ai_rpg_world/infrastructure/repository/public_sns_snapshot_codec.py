"""SNSの世界状態をJSONへ写し、すべて検査してから保存領域へ戻す。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ai_rpg_world.domain.sns.aggregate.base_sns_aggregate import BaseSnsContentAggregate
from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.exception.identity_token_exception import SnsIdentityValidationException
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.value_object.sns_identity_token import SnsIdentityToken
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.sqlite_sns_state_codec import (
    build_post_aggregate,
    build_reply_aggregate,
    build_user_aggregate,
)


def _content_row(content: BaseSnsContentAggregate[Any]) -> dict[str, Any]:
    return {
        'identity_token': content.identity_token,
        'author_user_id': content.author_user_id.value,
        'author_identity_token': content.author_identity_token,
        'content': content.content.content,
        'visibility': content.content.visibility.value,
        'deleted': int(content.deleted),
        'created_at': content.created_at.isoformat(),
        'hashtags': list(content.content.hashtags),
        'likes': [[like.user_id.value, like.created_at.isoformat()]
                  for like in sorted(content.likes, key=lambda item: item.user_id.value)],
        'mentions': sorted(mention.mentioned_user_name for mention in content.mentions),
    }


def _notification_row(notification: Notification) -> dict[str, Any]:
    content = notification.content
    return {
        'notification_id': notification.notification_id.value,
        'user_id': notification.user_id.value,
        'notification_type': notification.notification_type.value,
        'content': {
            'title': content.title, 'message': content.message,
            'actor_user_id': content.actor_user_id.value, 'actor_user_name': content.actor_user_name,
            'related_post_id': content.related_post_id.value if content.related_post_id else None,
            'related_reply_id': content.related_reply_id.value if content.related_reply_id else None,
            'content_type': content.content_type, 'content_text': content.content_text,
            'related_target_id': content.related_target_id, 'actor_identity_token': content.actor_identity_token,
        },
        'created_at': notification.created_at.isoformat(), 'is_read': notification.is_read,
        'expires_at': notification.expires_at.isoformat() if notification.expires_at else None,
        'identity_token': notification.identity_token, 'source_event_id': notification.source_event_id,
        'recipient_identity_token': notification.recipient_identity_token,
        'observation_delivered': notification.observation_delivered,
        'execution_provenance': notification.execution_provenance,
    }


def _restore_notification(row: dict[str, Any]) -> Notification:
    content = dict(row['content'])
    content['actor_user_id'] = UserId(content['actor_user_id'])
    if content['related_post_id'] is not None:
        content['related_post_id'] = PostId(content['related_post_id'])
    if content['related_reply_id'] is not None:
        content['related_reply_id'] = ReplyId(content['related_reply_id'])
    if type(row['is_read']) is not bool or type(row['observation_delivered']) is not bool:
        raise ValueError('SNS通知の既読状態が不正です')
    return Notification(
        notification_id=NotificationId(row['notification_id']), user_id=UserId(row['user_id']),
        notification_type=NotificationType(row['notification_type']), content=NotificationContent(**content),
        created_at=datetime.fromisoformat(row['created_at']), is_read=row['is_read'],
        expires_at=datetime.fromisoformat(row['expires_at']) if row['expires_at'] else None,
        identity_token=row['identity_token'], source_event_id=row['source_event_id'],
        recipient_identity_token=row['recipient_identity_token'],
        observation_delivered=row['observation_delivered'], execution_provenance=row['execution_provenance'],
    )


def capture_public_sns_store(store: InMemoryDataStore) -> dict[str, Any]:
    """ドメインイベントの待ち行列を含めず、SNSだけを決まった順に保存する。"""
    users = []
    for user in sorted(store.sns_users.values(), key=lambda item: item.user_id.value):
        users.append({
            'user_id': user.user_id.value, 'identity_token': user.identity_token,
            'user_name': user.profile.user_name, 'display_name': user.profile.display_name,
            'bio': user.profile.bio,
            'follows': sorted([rel.follower_user_id.value, rel.followee_user_id.value, rel.created_at.isoformat()]
                              for rel in user.follow_relationships),
            'blocks': sorted([rel.blocker_user_id.value, rel.blocked_user_id.value, rel.created_at.isoformat()]
                             for rel in user.block_relationships),
            'subscriptions': sorted([rel.subscriber_user_id.value, rel.subscribed_user_id.value, rel.created_at.isoformat()]
                                    for rel in user.subscribe_relationships),
        })
    posts = []
    for post in sorted(store.posts.values(), key=lambda item: item.post_id.value):
        posts.append({**_content_row(post), 'post_id': post.post_id.value,
                      'reply_ids': sorted(value.value for value in post.reply_ids)})
    replies = []
    for reply in sorted(store.replies.values(), key=lambda item: item.reply_id.value):
        replies.append({
            **_content_row(reply), 'reply_id': reply.reply_id.value,
            'parent_post_id': reply.parent_post_id.value if reply.parent_post_id else None,
            'parent_reply_id': reply.parent_reply_id.value if reply.parent_reply_id else None,
            'parent_identity_token': reply.parent_identity_token,
            'child_reply_ids': sorted(value.value for value in reply.reply_ids),
        })
    return {
        'schema_version': 1, 'namespace': store.sns_public_namespace,
        'users': users, 'posts': posts, 'replies': replies,
        'notifications': [_notification_row(notification) for notification in sorted(
            store.sns_notifications.values(), key=lambda item: item.notification_id.value)],
        'next_ids': {'users': store.sns_next_user_id, 'posts': store.next_post_id,
                     'replies': store.next_reply_id, 'notifications': store.next_sns_notification_id},
    }


def _rows(data: dict[str, Any], name: str) -> list[Any]:
    value = data.get(name)
    if not isinstance(value, list):
        raise ValueError(f'SNSの保存項目 {name} は一覧で指定してください')
    return value


def _unique(items: list[Any], id_attribute: str) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    tokens: set[str] = set()
    for item in items:
        key = getattr(item, id_attribute)
        token = item.identity_token
        if key in result or token in tokens:
            raise ValueError('SNSの保存対象が重複しています')
        result[key] = item
        tokens.add(token)
    return result


def restore_public_sns_store(store: InMemoryDataStore, payload: dict[str, Any]) -> None:
    """復元を検査し終わるまでは元の状態を変更せず、保存した識別子を再採番しない。"""
    if type(payload.get('schema_version')) is not int or payload['schema_version'] != 1:
        raise ValueError('SNSの保存形式に対応していません')
    try:
        namespace = SnsIdentityToken(payload['namespace']).value
    except SnsIdentityValidationException as exc:
        raise ValueError('SNSの名前空間が不正です') from exc
    users = _unique([build_user_aggregate(**row) for row in _rows(payload, 'users')], 'user_id')
    posts = _unique([build_post_aggregate(**row) for row in _rows(payload, 'posts')], 'post_id')
    replies = _unique([build_reply_aggregate(**row) for row in _rows(payload, 'replies')], 'reply_id')
    notifications = _unique([_restore_notification(row) for row in _rows(payload, 'notifications')], 'notification_id')
    usernames = {user.profile.user_name: user.user_id for user in users.values()}
    if len(usernames) != len(users):
        raise ValueError('SNSのアカウント名が重複しています')
    counters = payload.get('next_ids')
    if not isinstance(counters, dict):
        raise ValueError('SNSの採番位置がありません')
    for name, items in (('users', users), ('posts', posts), ('replies', replies), ('notifications', notifications)):
        value = counters.get(name)
        if type(value) is not int or value <= max((key.value for key in items), default=0):
            raise ValueError('SNSの採番位置が既存対象を上書きします')
    store.sns_public_namespace = namespace
    store.sns_users = users
    store.sns_username_to_user_id = usernames
    store.posts = posts
    store.replies = replies
    store.sns_notifications = notifications
    store.sns_next_user_id = counters['users']
    store.next_post_id = counters['posts']
    store.next_reply_id = counters['replies']
    store.next_sns_notification_id = counters['notifications']
