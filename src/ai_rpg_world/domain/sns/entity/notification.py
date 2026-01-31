from datetime import datetime
from typing import Optional
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent


class Notification(AggregateRoot):
    """通知エンティティ"""

    def __init__(
        self,
        notification_id: NotificationId,
        user_id: UserId,
        notification_type: NotificationType,
        content: NotificationContent,
        created_at: datetime,
        is_read: bool = False,
        expires_at: Optional[datetime] = None
    ):
        super().__init__()
        self._notification_id = notification_id
        self._user_id = user_id
        self._notification_type = notification_type
        self._content = content
        self._created_at = created_at
        self._is_read = is_read
        self._expires_at = expires_at

    @property
    def notification_id(self) -> NotificationId:
        """通知ID"""
        return self._notification_id

    @property
    def user_id(self) -> UserId:
        """通知対象ユーザーID"""
        return self._user_id

    @property
    def notification_type(self) -> NotificationType:
        """通知タイプ"""
        return self._notification_type

    @property
    def content(self) -> NotificationContent:
        """通知内容"""
        return self._content

    @property
    def created_at(self) -> datetime:
        """作成日時"""
        return self._created_at

    @property
    def is_read(self) -> bool:
        """既読状態"""
        return self._is_read

    @property
    def expires_at(self) -> Optional[datetime]:
        """有効期限（Noneの場合は中期通知）"""
        return self._expires_at

    def mark_as_read(self) -> None:
        """既読にする"""
        if not self._is_read:
            self._is_read = True

    def mark_as_unread(self) -> None:
        """未読にする"""
        if self._is_read:
            self._is_read = False

    def is_expired(self, current_time: datetime) -> bool:
        """有効期限切れかどうかを判定"""
        if self._expires_at is None:
            return False  # 中期通知は自動的に期限切れにならない
        return current_time > self._expires_at

    @classmethod
    def create_push_notification(
        cls,
        notification_id: NotificationId,
        user_id: UserId,
        notification_type: NotificationType,
        content: NotificationContent,
        expires_at: datetime,
        created_at: Optional[datetime] = None
    ) -> "Notification":
        """プッシュ通知を作成（一時的）"""
        if created_at is None:
            created_at = datetime.now()
        return cls(
            notification_id=notification_id,
            user_id=user_id,
            notification_type=notification_type,
            content=content,
            created_at=created_at,
            is_read=False,
            expires_at=expires_at
        )

    @classmethod
    def create_persistent_notification(
        cls,
        notification_id: NotificationId,
        user_id: UserId,
        notification_type: NotificationType,
        content: NotificationContent,
        created_at: Optional[datetime] = None
    ) -> "Notification":
        """中期通知を作成（永続的）"""
        if created_at is None:
            created_at = datetime.now()
        return cls(
            notification_id=notification_id,
            user_id=user_id,
            notification_type=notification_type,
            content=content,
            created_at=created_at,
            is_read=False,
            expires_at=None  # 中期通知は自動削除されない
        )
