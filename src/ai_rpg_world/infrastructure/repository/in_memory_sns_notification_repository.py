"""
InMemorySnsNotificationRepository - Notificationを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from datetime import datetime
from ai_rpg_world.domain.sns.repository.sns_notification_repository import SnsNotificationRepository
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemorySnsNotificationRepository(SnsNotificationRepository, InMemoryRepositoryBase):
    """Notificationを使用するインメモリリポジトリ"""

    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)

    @property
    def _notifications(self) -> Dict[NotificationId, Notification]:
        return self._data_store.sns_notifications

    def clear(self) -> None:
        """全通知をクリア（テスト用）"""
        self._notifications.clear()
        self._data_store.next_sns_notification_id = 1

    def generate_notification_id(self) -> NotificationId:
        """通知IDを生成"""
        notification_id = NotificationId(self._data_store.next_sns_notification_id)
        self._data_store.next_sns_notification_id += 1
        return notification_id

    def save(self, notification: Notification) -> Notification:
        """通知を保存"""
        cloned_notification = self._clone(notification)
        def operation():
            self._notifications[cloned_notification.notification_id] = cloned_notification
            return cloned_notification
            
        self._register_aggregate(notification)
        return self._execute_operation(operation)

    def find_by_id(self, notification_id: NotificationId) -> Optional[Notification]:
        """通知IDで通知を取得"""
        return self._clone(self._notifications.get(notification_id))

    def find_by_user_id(self, user_id: UserId, limit: int = 50, offset: int = 0) -> List[Notification]:
        """ユーザーIDで通知を取得（新しい順）"""
        user_notifications = [
            self._clone(notification) for notification in self._notifications.values()
            if notification.user_id == user_id
        ]
        user_notifications.sort(key=lambda n: n.created_at, reverse=True)
        return user_notifications[offset:offset + limit]

    def find_unread_by_user_id(self, user_id: UserId) -> List[Notification]:
        """ユーザーIDで未読通知を取得"""
        return [
            self._clone(notification) for notification in self._notifications.values()
            if notification.user_id == user_id and not notification.is_read
        ]

    def mark_as_read(self, notification_id: NotificationId) -> None:
        """通知を既読にする"""
        notification = self._notifications.get(notification_id)
        if not notification:
            return
            
        def operation():
            target = self._notifications.get(notification_id)
            if target:
                target.mark_as_read()
                
        self._register_aggregate(notification)
        self._execute_operation(operation)

    def mark_all_as_read(self, user_id: UserId) -> None:
        """ユーザーの全通知を既読にする"""
        # 未読通知を特定して登録
        unread_notifications = [n for n in self._notifications.values() if n.user_id == user_id and not n.is_read]
        for n in unread_notifications:
            self._register_aggregate(n)
            
        def operation():
            for notification in unread_notifications:
                notification.mark_as_read()
                    
        self._execute_operation(operation)

    def delete_expired_notifications(self, current_time: datetime) -> int:
        """期限切れ通知を削除"""
        def operation():
            expired_ids = [
                notification_id for notification_id, notification in self._notifications.items()
                if notification.is_expired(current_time)
            ]
            for notification_id in expired_ids:
                del self._notifications[notification_id]
            return len(expired_ids)
            
        return self._execute_operation(operation)

    def delete_old_notifications(self, user_id: UserId, keep_count: int = 100) -> int:
        """古い通知を削除"""
        def operation():
            user_notifications = [
                (notification_id, notification) for notification_id, notification in self._notifications.items()
                if notification.user_id == user_id and notification.expires_at is None
            ]
            user_notifications.sort(key=lambda n: n[1].created_at)
            if len(user_notifications) > keep_count:
                notifications_to_delete = user_notifications[:len(user_notifications) - keep_count]
                deleted_count = len(notifications_to_delete)
                for notification_id, _ in notifications_to_delete:
                    del self._notifications[notification_id]
                return deleted_count
            return 0
            
        return self._execute_operation(operation)

    def get_unread_count(self, user_id: UserId) -> int:
        """未読通知数を取得"""
        return len([
            notification for notification in self._notifications.values()
            if notification.user_id == user_id and not notification.is_read
        ])

    def find_by_ids(self, notification_ids: List[NotificationId]) -> List[Notification]:
        """IDのリストで通知を検索"""
        return [
            self._notifications[notification_id]
            for notification_id in notification_ids
            if notification_id in self._notifications
        ]

    def delete(self, notification_id: NotificationId) -> bool:
        """通知を削除"""
        def operation():
            if notification_id in self._notifications:
                del self._notifications[notification_id]
                return True
            return False
            
        return self._execute_operation(operation)

    def find_all(self) -> List[Notification]:
        """全ての通知を取得"""
        return list(self._notifications.values())
