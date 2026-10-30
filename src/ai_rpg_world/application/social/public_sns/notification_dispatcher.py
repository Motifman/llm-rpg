"""公開条件を再検査して、通知を投稿と同じ確定境界へ保存する。"""

from __future__ import annotations

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.application.social.public_sns.access_policy import PublicSnsAccessPolicy
from ai_rpg_world.application.social.public_sns.command_repository import PublicSnsCommandRepositories
from ai_rpg_world.application.social.public_sns.contracts import PublicSnsUnavailableError
from ai_rpg_world.application.social.public_sns.notification_events import (
    PublicSnsActivityEvent,
    PublicSnsNotificationReadyEvent,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.value_object.user_id import UserId


class PublicSnsNotificationDispatcher:
    """外部配送を一切せず、重複しない通知と配送候補だけを記録する。"""

    def dispatch(self, event: DomainEvent, context: CommandContext[PublicSnsCommandRepositories]) -> None:
        if not isinstance(event, PublicSnsActivityEvent):
            return
        repos = context.repositories
        access = PublicSnsAccessPolicy(repos.read)
        actor = repos.read.find_user(event.actor_user_id)
        if actor is None or actor.identity_token != event.actor_identity_token:
            return
        for recipient_id, recipient_token, kind in event.recipients:
            if recipient_id == event.actor_user_id:
                continue
            recipient = repos.read.find_user(recipient_id)
            if recipient is None or recipient.identity_token != recipient_token:
                continue
            if not access.users_can_interact(recipient_id, event.actor_user_id):
                continue
            if kind not in {"mention", "reply", "like", "follow"}:
                continue
            target = None
            if event.target_id is not None:
                try:
                    target = access.require_visible_target(recipient_id, event.target_id)
                    # 通知の使う側にも全祖先が現在公開されている必要がある。
                    access.require_visible_target(event.actor_user_id, event.target_id)
                except PublicSnsUnavailableError:
                    continue
            if target is None and kind != "follow":
                continue
            source = str(event.event_id)
            if repos.notification_exists(source, recipient_token, kind):
                continue
            content = NotificationContent(
                title={"reply": "新しい返信", "mention": "メンション", "like": "いいね", "follow": "新しいフォロワー"}[
                    kind
                ],
                message=f"{actor.display_name}さんからのSNS通知",
                actor_user_id=UserId(actor.user_id),
                actor_user_name=actor.display_name,
                related_post_id=PostId(target.local_id) if target and target.kind == "post" else None,
                related_reply_id=ReplyId(target.local_id) if target and target.kind == "reply" else None,
                content_type=target.kind if target else None,
                content_text=target.content if target else None,
                related_target_id=event.target_id,
                actor_identity_token=actor.identity_token,
            )
            notification = Notification(
                notification_id=repos.notifications.generate_notification_id(),
                user_id=UserId(recipient_id),
                notification_type=NotificationType(kind),
                content=content,
                created_at=event.occurred_at,
                source_event_id=source,
                recipient_identity_token=recipient_token,
                execution_provenance=event.provenance.to_dict() if event.provenance else None,
            )
            repos.notifications.save(notification)
            context.collect(
                PublicSnsNotificationReadyEvent.create(
                    aggregate_id=notification.identity_token,
                    aggregate_type="PublicSnsNotification",
                    notification_id=notification.notification_id.value,
                    notification_identity_token=notification.identity_token,
                )
            )
