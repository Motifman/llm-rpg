"""
InMemorySnsNotificationRepository - Notificationを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from datetime import datetime
from src.domain.sns.repository.sns_notification_repository import SnsNotificationRepository
from src.domain.sns.entity.notification import Notification
from src.domain.sns.value_object.notification_id import NotificationId
from src.domain.sns.value_object.user_id import UserId


class InMemorySnsNotificationRepository(SnsNotificationRepository):
    """Notificationを使用するインメモリリポジトリ"""

    def __init__(self):
        self._notifications: Dict[NotificationId, Notification] = {}
        self._next_notification_id = NotificationId(1)

    def clear(self) -> None:
        """全通知をクリア（テスト用）"""
        self._notifications.clear()
        self._next_notification_id = NotificationId(1)

    def generate_notification_id(self) -> NotificationId:
        """通知IDを生成"""
        notification_id = self._next_notification_id
        self._next_notification_id = NotificationId(self._next_notification_id.value + 1)
        return notification_id

    def save(self, notification: Notification) -> None:
        """通知を保存"""
        self._notifications[notification.notification_id] = notification

    def find_by_id(self, notification_id: NotificationId) -> Optional[Notification]:
        """通知IDで通知を取得"""
        return self._notifications.get(notification_id)

    def find_by_user_id(self, user_id: UserId, limit: int = 50, offset: int = 0) -> List[Notification]:
        """ユーザーIDで通知を取得（新しい順）"""
        user_notifications = [
            notification for notification in self._notifications.values()
            if notification.user_id == user_id
        ]

        # 新しい順にソート
        user_notifications.sort(key=lambda n: n.created_at, reverse=True)

        # ページング
        start_index = offset
        end_index = offset + limit
        return user_notifications[start_index:end_index]

    def find_unread_by_user_id(self, user_id: UserId) -> List[Notification]:
        """ユーザーIDで未読通知を取得"""
        return [
            notification for notification in self._notifications.values()
            if notification.user_id == user_id and not notification.is_read
        ]

    def mark_as_read(self, notification_id: NotificationId) -> None:
        """通知を既読にする"""
        notification = self._notifications.get(notification_id)
        if notification:
            notification.mark_as_read()

    def mark_all_as_read(self, user_id: UserId) -> None:
        """ユーザーの全通知を既読にする"""
        for notification in self._notifications.values():
            if notification.user_id == user_id:
                notification.mark_as_read()

    def delete_expired_notifications(self, current_time: datetime) -> int:
        """期限切れ通知を削除（プッシュ通知用）"""
        expired_ids = [
            notification_id for notification_id, notification in self._notifications.items()
            if notification.is_expired(current_time)
        ]

        for notification_id in expired_ids:
            del self._notifications[notification_id]

        return len(expired_ids)

    def delete_old_notifications(self, user_id: UserId, keep_count: int = 100) -> int:
        """古い通知を削除（中期通知用）"""
        user_notifications = [
            (notification_id, notification) for notification_id, notification in self._notifications.items()
            if notification.user_id == user_id and notification.expires_at is None
        ]

        # 作成日時でソート（古い順）
        user_notifications.sort(key=lambda n: n[1].created_at)

        # 保持数を超える古い通知を削除
        if len(user_notifications) > keep_count:
            notifications_to_delete = user_notifications[:len(user_notifications) - keep_count]
            deleted_count = len(notifications_to_delete)

            for notification_id, _ in notifications_to_delete:
                del self._notifications[notification_id]

            return deleted_count

        return 0

    def get_unread_count(self, user_id: UserId) -> int:
        """未読通知数を取得"""
        return len([
            notification for notification in self._notifications.values()
            if notification.user_id == user_id and not notification.is_read
        ])
