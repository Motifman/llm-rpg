import logging
from typing import List, TYPE_CHECKING, Callable, Any, Optional
from datetime import datetime, timedelta
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
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.user_id import UserId

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.repository.sns_user_repository import SnsUserRepository
    from ai_rpg_world.domain.sns.repository.sns_notification_repository import SnsNotificationRepository
    from ai_rpg_world.domain.sns.repository.post_repository import PostRepository
    from ai_rpg_world.domain.sns.repository.reply_repository import ReplyRepository
    from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
    from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate


class NotificationEventHandlerService:
    """通知関連イベントハンドラサービス"""

    def __init__(
        self,
        user_repository: "SnsUserRepository",
        notification_repository: "SnsNotificationRepository",
        post_repository: "PostRepository",
        reply_repository: "ReplyRepository",
        unit_of_work_factory: UnitOfWorkFactory  # ファクトリインスタンスを使用
    ):
        self._user_repository = user_repository
        self._notification_repository = notification_repository
        self._post_repository = post_repository
        self._reply_repository = reply_repository
        self._unit_of_work_factory = unit_of_work_factory  # Unit of Workファクトリ
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_in_separate_transaction(self, operation: Callable[[], Any], context: dict) -> None:
        """別トランザクションで操作を実行し、共通の例外処理を行う"""
        unit_of_work = self._unit_of_work_factory.create()
        try:
            with unit_of_work:
                operation()
        except Exception as e:
            self._logger.error(f"Failed to handle event in {context.get('handler', 'unknown')}: {str(e)}",
                             extra=context, exc_info=True)
            # イベントハンドラなので、例外を再スローせず処理を継続


    def handle_user_subscribed(self, event: SnsUserSubscribedEvent) -> None:
        """ユーザーサブスクライブ時の通知処理"""
        self._logger.info(f"Processing user subscribed event: subscriber={event.subscriber_user_id}, subscribed={event.subscribed_user_id}")

        def operation():
            # サブスクライバーとサブスクライブされたユーザーを取得
            subscriber = self._user_repository.find_by_id(event.subscriber_user_id)
            if subscriber is None:
                self._logger.warning(f"Subscriber not found: {event.subscriber_user_id}")
                return  # サブスクライバーが存在しない場合は処理しない

            subscribed = self._user_repository.find_by_id(event.subscribed_user_id)
            if subscribed is None:
                self._logger.warning(f"Subscribed user not found: {event.subscribed_user_id}")
                return  # サブスクライブ対象が存在しない場合は処理しない

            # 通知作成
            notification = self._create_subscribe_notification(subscriber, subscribed)

            # 通知保存
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
            # フォロワーとフォローされたユーザーを取得
            follower = self._user_repository.find_by_id(event.follower_user_id)
            if follower is None:
                self._logger.warning(f"Follower not found: {event.follower_user_id}")
                return  # フォロワーが存在しない場合は処理しない

            followee = self._user_repository.find_by_id(event.followee_user_id)
            if followee is None:
                self._logger.warning(f"Followee not found: {event.followee_user_id}")
                return  # フォロー対象が存在しない場合は処理しない

            # 通知作成
            notification = self._create_follow_notification(follower, followee)

            # 通知保存
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
            # ポスト作成者を取得
            author = self._user_repository.find_by_id(event.author_user_id)
            if author is None:
                self._logger.warning(f"Post author not found: {event.author_user_id}")
                return

            notifications_to_save = []

            # 1. メンション通知の作成
            if event.mentions:
                # メンションされたユーザー名からユーザーIDを取得
                mentioned_user_ids = set()
                for mention in event.mentions:
                    mentioned_user = self._user_repository.find_by_display_name(mention.mentioned_user_name)
                    if mentioned_user is not None:
                        mentioned_user_ids.add(mentioned_user.user_id)

                # メンションされたユーザーのリストを取得
                mentioned_users = []
                for user_id in mentioned_user_ids:
                    user = self._user_repository.find_by_id(user_id)
                    if user is not None and user.user_id != author.user_id:  # 自分へのメンションは除外
                        mentioned_users.append(user)

                if mentioned_users:
                    # ポストの内容を取得
                    post_content_text = event.content.content
                    mention_notifications = self._create_mention_notifications(
                        author, mentioned_users, "post", event.post_id.value, post_content_text
                    )
                    notifications_to_save.extend(mention_notifications)

            # 2. サブスクライバーへの通知
            # ポストの内容を取得
            post_content_text = event.content.content
            subscriber_user_ids = self._user_repository.find_subscribers(author.user_id)

            if subscriber_user_ids:
                subscriber_users = []
                for subscriber_id in subscriber_user_ids:
                    subscriber = self._user_repository.find_by_id(subscriber_id)
                    if subscriber is not None:
                        subscriber_users.append(subscriber)

                if subscriber_users:
                    subscriber_notifications = self._create_subscriber_notifications(
                        author, subscriber_users, post_content_text
                    )
                    notifications_to_save.extend(subscriber_notifications)

            # 通知保存
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
            # リプライ作成者を取得
            replier = self._user_repository.find_by_id(event.author_user_id)
            if replier is None:
                self._logger.warning(f"Reply author not found: {event.author_user_id}")
                return

            notifications_to_save = []

            # 1. メンション通知の作成
            if event.mentions:
                # メンションされたユーザー名からユーザーIDを取得
                mentioned_user_ids = set()
                for mention in event.mentions:
                    mentioned_user = self._user_repository.find_by_display_name(mention.mentioned_user_name)
                    if mentioned_user is not None:
                        mentioned_user_ids.add(mentioned_user.user_id)

                # メンションされたユーザーのリストを取得
                mentioned_users = []
                for user_id in mentioned_user_ids:
                    user = self._user_repository.find_by_id(user_id)
                    if user is not None and user.user_id != replier.user_id:  # 自分へのメンションは除外
                        mentioned_users.append(user)

                if mentioned_users:
                    # リプライの内容を取得
                    reply_content_text = event.content.content
                    mention_notifications = self._create_mention_notifications(
                        replier, mentioned_users, "reply", event.reply_id.value, reply_content_text
                    )
                    notifications_to_save.extend(mention_notifications)

            # 2. 親コンテンツ作成者への返信通知
            if event.parent_author_id is not None and event.parent_author_id != replier.user_id:
                # 自分への返信は通知しない
                content_type = "reply" if event.parent_reply_id is not None else "post"
                content_id = event.parent_reply_id.value if event.parent_reply_id is not None else event.parent_post_id.value

                parent_author = self._user_repository.find_by_id(event.parent_author_id)
                if parent_author is not None:
                    # 返信の内容（リプライの内容）を取得
                    content_text = event.content.content

                    reply_notification = self._create_reply_notification(
                        replier, parent_author, content_type, content_id, content_text
                    )
                    notifications_to_save.append(reply_notification)

            # 通知保存
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
            # いいねしたユーザーとコンテンツ作成者を取得
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
                return  # 自分へのいいねの場合は処理しない

            # いいねされたコンテンツの内容を取得
            if event.content_type == "post":
                liked_content = self._post_repository.find_by_id(event.target_id)
                content_text = liked_content.content.content if liked_content is not None else None
            else:  # reply
                liked_content = self._reply_repository.find_by_id(event.target_id)
                content_text = liked_content.content.content if liked_content is not None else None

            # 通知作成
            notification = self._create_like_notification(
                liker, content_author, event.content_type, event.target_id.value, content_text
            )

            # 通知保存
            self._notification_repository.save(notification)

            self._logger.info(f"Successfully created like notification for user {event.content_author_id}")

        self._execute_in_separate_transaction(operation, {
            "handler": "handle_content_liked",
            "liker_id": event.user_id,
            "content_author_id": event.content_author_id,
            "content_type": event.content_type,
            "target_id": event.target_id.value
        })

    def _create_subscribe_notification(
        self,
        subscriber: "UserAggregate",
        subscribed: "UserAggregate"
    ) -> Notification:
        """サブスクライブ通知作成（プライベートメソッド）"""
        notification_id = self._notification_repository.generate_notification_id()
        content = NotificationContent.create_subscribe_notification(
            subscriber_user_id=subscriber.user_id,
            subscriber_user_name=subscriber.profile.display_name
        )

        return Notification.create_persistent_notification(
            notification_id=notification_id,
            user_id=subscribed.user_id,
            notification_type=NotificationType.SUBSCRIBE,
            content=content
        )

    def _create_follow_notification(
        self,
        follower: "UserAggregate",
        followee: "UserAggregate"
    ) -> Notification:
        """フォロー通知作成（プライベートメソッド）"""
        notification_id = self._notification_repository.generate_notification_id()
        content = NotificationContent.create_follow_notification(
            follower_user_id=follower.user_id,
            follower_user_name=follower.profile.display_name
        )

        return Notification.create_persistent_notification(
            notification_id=notification_id,
            user_id=followee.user_id,
            notification_type=NotificationType.FOLLOW,
            content=content
        )

    def _create_mention_notifications(
        self,
        mentioner: "UserAggregate",
        mentioned_users: List["UserAggregate"],
        content_type: str,
        content_id: int,
        content_text: Optional[str] = None
    ) -> List[Notification]:
        """メンション通知作成（プライベートメソッド）"""
        notifications = []

        for mentioned_user in mentioned_users:
            notification_id = self._notification_repository.generate_notification_id()
            content = NotificationContent.create_mention_notification(
                mentioner_user_id=mentioner.user_id,
                mentioner_user_name=mentioner.profile.display_name,
                content_type=content_type,
                content_id=content_id,
                content_text=content_text
            )

            notification = Notification.create_persistent_notification(
                notification_id=notification_id,
                user_id=mentioned_user.user_id,
                notification_type=NotificationType.MENTION,
                content=content
            )
            notifications.append(notification)

        return notifications

    def _create_like_notification(
        self,
        liker: "UserAggregate",
        content_author: "UserAggregate",
        content_type: str,
        content_id: int,
        content_text: Optional[str] = None
    ) -> Notification:
        """いいね通知作成（プライベートメソッド）"""
        notification_id = self._notification_repository.generate_notification_id()
        content = NotificationContent.create_like_notification(
            liker_user_id=liker.user_id,
            liker_user_name=liker.profile.display_name,
            content_type=content_type,
            content_id=content_id,
            content_text=content_text
        )

        return Notification.create_persistent_notification(
            notification_id=notification_id,
            user_id=content_author.user_id,
            notification_type=NotificationType.LIKE,
            content=content
        )

    def _create_reply_notification(
        self,
        replier: "UserAggregate",
        parent_author: "UserAggregate",
        content_type: str,
        content_id: int,
        content_text: Optional[str] = None
    ) -> Notification:
        """返信通知作成（プライベートメソッド）"""
        notification_id = self._notification_repository.generate_notification_id()
        content = NotificationContent.create_reply_notification(
            replier_user_id=replier.user_id,
            replier_user_name=replier.profile.display_name,
            content_type=content_type,
            content_id=content_id,
            content_text=content_text
        )

        return Notification.create_persistent_notification(
            notification_id=notification_id,
            user_id=parent_author.user_id,
            notification_type=NotificationType.REPLY,
            content=content
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

    def _create_subscriber_notifications(
        self,
        author: "UserAggregate",
        subscribers: List["UserAggregate"],
        post_content: str
    ) -> List[Notification]:
        """サブスクライバー通知作成（プライベートメソッド）"""
        notifications = []

        for subscriber in subscribers:
            notification_id = self._notification_repository.generate_notification_id()
            content = NotificationContent.create_post_notification(
                author_user_id=author.user_id,
                author_user_name=author.profile.display_name,
                content_text=post_content
            )

            notification = Notification.create_persistent_notification(
                notification_id=notification_id,
                user_id=subscriber.user_id,
                notification_type=NotificationType.POST,
                content=content
            )
            notifications.append(notification)

        return notifications
