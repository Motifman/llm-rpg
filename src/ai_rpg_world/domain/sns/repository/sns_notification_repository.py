from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.entity.notification import Notification


class SnsNotificationRepository(Repository[Notification, NotificationId], ABC):
    """SNS通知リポジトリインターフェース"""

    @abstractmethod
    def generate_notification_id(self) -> NotificationId:
        """新しいNotificationIdを生成"""
        pass

    @abstractmethod
    def save(self, notification: Notification) -> None:
        """通知を保存"""
        pass

    @abstractmethod
    def find_by_id(self, notification_id: NotificationId) -> Optional[Notification]:
        """通知IDで通知を取得"""
        pass

    @abstractmethod
    def find_by_user_id(self, user_id: UserId, limit: int = 50, offset: int = 0) -> List[Notification]:
        """ユーザーIDで通知を取得（新しい順）"""
        pass

    @abstractmethod
    def find_unread_by_user_id(self, user_id: UserId) -> List[Notification]:
        """ユーザーIDで未読通知を取得"""
        pass

    @abstractmethod
    def mark_as_read(self, notification_id: NotificationId) -> None:
        """通知を既読にする"""
        pass

    @abstractmethod
    def mark_all_as_read(self, user_id: UserId) -> None:
        """ユーザーの全通知を既読にする"""
        pass

    @abstractmethod
    def delete_expired_notifications(self, current_time: datetime) -> int:
        """期限切れ通知を削除（プッシュ通知用）"""
        pass

    @abstractmethod
    def delete_old_notifications(self, user_id: UserId, keep_count: int = 100) -> int:
        """古い通知を削除（中期通知用）"""
        pass

    @abstractmethod
    def get_unread_count(self, user_id: UserId) -> int:
        """未読通知数を取得"""
        pass
