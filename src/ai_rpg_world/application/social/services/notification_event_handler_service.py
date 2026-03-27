import logging
from typing import List, TYPE_CHECKING, Callable, Any, Optional, FrozenSet
from datetime import datetime, timedelta
from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.sns.event import (
    SnsUserSubscribedEvent,
    SnsUserFollowedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsContentLikedEvent,
)
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.user_id import UserId

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.repository.sns_user_repository import SnsUserRepository
    from ai_rpg_world.domain.sns.repository.sns_notification_repository import SnsNotificationRepository
    from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class NotificationEventHandlerService:
    """通知関連イベントハンドラサービス"""

    def __init__(
        self,
        user_repository: "SnsUserRepository",
        notification_repository: "SnsNotificationRepository",
        unit_of_work_factory: UnitOfWorkFactory  # ファクトリインスタンスを使用
    ):
        self._user_repository = user_repository
        self._notification_repository = notification_repository
        self._unit_of_work_factory = unit_of_work_factory  # Unit of Workファクトリ
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_in_separate_transaction(self, operation: Callable[[], Any], context: dict) -> None:
        """別トランザクションで操作を実行。ApplicationException/DomainException は再送出、その他は SystemErrorException でラップして送出する。"""
        unit_of_work = self._unit_of_work_factory.create()
        try:
            with unit_of_work:
                operation()
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Failed to handle event in %s: %s",
                context.get("handler", "unknown"),
                e,
                extra=context,
            )
            raise SystemErrorException(
                f"Notification event handling failed in {context.get('handler', 'unknown')}: {e}",
                original_exception=e,
            ) from e

    def handle_user_subscribed(self, event: SnsUserSubscribedEvent) -> None:
        """ユーザーサブスクライブ時の通知処理"""
        self._logger.info(f"Processing user subscribed event: subscriber={event.subscriber_user_id}, subscribed={event.subscribed_user_id}")

        def operation():
            subscriber = self._user_repository.find_by_id(event.subscriber_user_id)
            if subscriber is None:
                self._logger.warning(f"Subscriber not found: {event.subscriber_user_id}")
                return
            subscribed = self._user_repository.find_by_id(event.subscribed_user_id)
            if subscribed is None:
                self._logger.warning(f"Subscribed user not found: {event.subscribed_user_id}")
                return

            subscriber_name = event.subscriber_display_name or subscriber.profile.display_name
            notification_id = self._notification_repository.generate_notification_id()
            content = NotificationContent.create_subscribe_notification(
                subscriber_user_id=event.subscriber_user_id,
                subscriber_user_name=subscriber_name,
            )
            notification = Notification.create_persistent_notification(
                notification_id=notification_id,
                user_id=event.subscribed_user_id,
                notification_type=NotificationType.SUBSCRIBE,
                content=content,
            )
            self._notification_repository.save(notification)

            self._logger.info(f"Successfully created subscribe notification for user {event.subscribed_user_id}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_user_subscribed",
            "subscriber_id": event.subscriber_user_id,
            "subscribed_id": event.subscribed_user_id
        })

    def handle_user_followed(self, event: SnsUserFollowedEvent) -> None:
        """ユーザーフォロー時の通知処理"""
        self._logger.info(f"Processing user followed event: follower={event.follower_user_id}, followee={event.followee_user_id}")

        def operation():
            follower = self._user_repository.find_by_id(event.follower_user_id)
            if follower is None:
                self._logger.warning(f"Follower not found: {event.follower_user_id}")
                return
            followee = self._user_repository.find_by_id(event.followee_user_id)
            if followee is None:
                self._logger.warning(f"Followee not found: {event.followee_user_id}")
                return

            follower_name = event.follower_display_name or follower.profile.display_name
            notification_id = self._notification_repository.generate_notification_id()
            content = NotificationContent.create_follow_notification(
                follower_user_id=event.follower_user_id,
                follower_user_name=follower_name,
            )
            notification = Notification.create_persistent_notification(
                notification_id=notification_id,
                user_id=event.followee_user_id,
                notification_type=NotificationType.FOLLOW,
                content=content,
            )
            self._notification_repository.save(notification)

            self._logger.info(f"Successfully created follow notification for user {event.followee_user_id}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_user_followed",
            "follower_id": event.follower_user_id,
            "followee_id": event.followee_user_id
        })

    def handle_post_created(self, event: SnsPostCreatedEvent) -> None:
        """ポスト作成時の通知処理"""
        self._logger.info(f"Processing post created event: author={event.author_user_id}, post_id={event.post_id}")

        def operation():
            notifications_to_save: List[Notification] = []
            author_id = event.author_user_id
            author_name = event.author_display_name
            post_content_text = event.content.content

            mention_targets = frozenset(
                uid for uid in event.mentioned_user_ids if uid.value != author_id.value
            )
            if mention_targets:
                notifications_to_save.extend(
                    self._mention_notifications_for_users(
                        mentioner_user_id=author_id,
                        mentioner_user_name=author_name,
                        mentioned_user_ids=mention_targets,
                        content_type="post",
                        content_id=event.post_id.value,
                        content_text=post_content_text,
                    )
                )

            for subscriber_uid in event.subscriber_user_ids:
                if subscriber_uid.value == author_id.value:
                    continue
                notifications_to_save.append(
                    self._single_subscriber_post_notification(
                        author_user_id=author_id,
                        author_user_name=author_name,
                        subscriber_user_id=subscriber_uid,
                        post_content=post_content_text,
                    )
                )

            for notification in notifications_to_save:
                self._notification_repository.save(notification)

            self._logger.info(f"Successfully created {len(notifications_to_save)} notifications for post {event.post_id}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_post_created",
            "author_id": event.author_user_id,
            "post_id": event.post_id
        })

    def handle_reply_created(self, event: SnsReplyCreatedEvent) -> None:
        """リプライ作成時の通知処理"""
        self._logger.info(f"Processing reply created event: author={event.author_user_id}, reply_id={event.reply_id}")

        def operation():
            notifications_to_save: List[Notification] = []
            replier_id = event.author_user_id
            replier_name = event.author_display_name
            reply_text = event.content.content

            mention_targets = frozenset(
                uid for uid in event.mentioned_user_ids if uid.value != replier_id.value
            )
            if mention_targets:
                notifications_to_save.extend(
                    self._mention_notifications_for_users(
                        mentioner_user_id=replier_id,
                        mentioner_user_name=replier_name,
                        mentioned_user_ids=mention_targets,
                        content_type="reply",
                        content_id=event.reply_id.value,
                        content_text=reply_text,
                    )
                )

            if event.parent_author_id is not None and event.parent_author_id != replier_id:
                content_type = "reply" if event.parent_reply_id is not None else "post"
                content_id = (
                    event.parent_reply_id.value
                    if event.parent_reply_id is not None
                    else event.parent_post_id.value
                )
                notification_id = self._notification_repository.generate_notification_id()
                content = NotificationContent.create_reply_notification(
                    replier_user_id=replier_id,
                    replier_user_name=replier_name,
                    content_type=content_type,
                    content_id=content_id,
                    content_text=reply_text,
                )
                notifications_to_save.append(
                    Notification.create_persistent_notification(
                        notification_id=notification_id,
                        user_id=event.parent_author_id,
                        notification_type=NotificationType.REPLY,
                        content=content,
                    )
                )

            for notification in notifications_to_save:
                self._notification_repository.save(notification)

            self._logger.info(f"Successfully created {len(notifications_to_save)} notifications for reply {event.reply_id}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_reply_created",
            "author_id": event.author_user_id,
            "reply_id": event.reply_id
        })

    def handle_content_liked(self, event: SnsContentLikedEvent) -> None:
        """コンテンツいいね時の通知処理"""
        self._logger.info(f"Processing content liked event: liker={event.user_id}, content_author={event.content_author_id}")

        def operation():
            liker = self._user_repository.find_by_id(event.user_id)
            content_author = self._user_repository.find_by_id(event.content_author_id)

            if liker is None:
                self._logger.warning(f"Liker not found: {event.user_id}")
                return
            if content_author is None:
                self._logger.warning(f"Content author not found: {event.content_author_id}")
                return
            if liker.user_id == content_author.user_id:
                self._logger.debug(f"Self-like detected, skipping notification: {event.user_id}")
                return

            liker_name = event.liker_display_name or liker.profile.display_name
            notification_id = self._notification_repository.generate_notification_id()
            content = NotificationContent.create_like_notification(
                liker_user_id=liker.user_id,
                liker_user_name=liker_name,
                content_type=event.content_type,
                content_id=event.target_id.value,
                content_text=event.content_text or None,
            )
            notification = Notification.create_persistent_notification(
                notification_id=notification_id,
                user_id=content_author.user_id,
                notification_type=NotificationType.LIKE,
                content=content,
            )
            self._notification_repository.save(notification)

            self._logger.info(f"Successfully created like notification for user {event.content_author_id}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_content_liked",
            "liker_id": event.user_id,
            "content_author_id": event.content_author_id,
            "content_type": event.content_type,
            "target_id": event.target_id.value
        })

    def _mention_notifications_for_users(
        self,
        mentioner_user_id: UserId,
        mentioner_user_name: str,
        mentioned_user_ids: FrozenSet[UserId],
        content_type: str,
        content_id: int,
        content_text: Optional[str],
    ) -> List[Notification]:
        notifications: List[Notification] = []
        for mentioned_uid in mentioned_user_ids:
            notification_id = self._notification_repository.generate_notification_id()
            content = NotificationContent.create_mention_notification(
                mentioner_user_id=mentioner_user_id,
                mentioner_user_name=mentioner_user_name,
                content_type=content_type,
                content_id=content_id,
                content_text=content_text,
            )
            notifications.append(
                Notification.create_persistent_notification(
                    notification_id=notification_id,
                    user_id=mentioned_uid,
                    notification_type=NotificationType.MENTION,
                    content=content,
                )
            )
        return notifications

    def _single_subscriber_post_notification(
        self,
        author_user_id: UserId,
        author_user_name: str,
        subscriber_user_id: UserId,
        post_content: str,
    ) -> Notification:
        notification_id = self._notification_repository.generate_notification_id()
        content = NotificationContent.create_post_notification(
            author_user_id=author_user_id,
            author_user_name=author_user_name,
            content_text=post_content,
        )
        return Notification.create_persistent_notification(
            notification_id=notification_id,
            user_id=subscriber_user_id,
            notification_type=NotificationType.POST,
            content=content,
        )

    def _create_push_notification(
        self,
        user_id: UserId,
        notification_type: NotificationType,
        content: NotificationContent,
        expires_in_minutes: int = 5
    ) -> Notification:
        """プッシュ通知作成（プライベートメソッド）"""
        notification_id = self._notification_repository.generate_notification_id()
        expires_at = datetime.now() + timedelta(minutes=expires_in_minutes)

        return Notification.create_push_notification(
            notification_id=notification_id,
            user_id=user_id,
            notification_type=notification_type,
            content=content,
            expires_at=expires_at
        )
