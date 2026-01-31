import pytest
from datetime import datetime, timedelta
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType
from ai_rpg_world.domain.sns.value_object.notification_content import NotificationContent


class TestNotificationEntity:
    """Notificationエンティティのテスト"""

    @pytest.fixture
    def sample_notification_id(self):
        return NotificationId(1)

    @pytest.fixture
    def sample_user_id(self):
        return UserId(100)

    @pytest.fixture
    def sample_content(self):
        return NotificationContent.create_follow_notification(UserId(200), "follower")

    @pytest.fixture
    def sample_created_at(self):
        return datetime(2024, 1, 1, 12, 0, 0)

    def test_create_push_notification(self, sample_notification_id, sample_user_id, sample_content, sample_created_at):
        """プッシュ通知の作成テスト"""
        expires_at = sample_created_at + timedelta(minutes=5)

        notification = Notification.create_push_notification(
            notification_id=sample_notification_id,
            user_id=sample_user_id,
            notification_type=NotificationType.FOLLOW,
            content=sample_content,
            expires_at=expires_at,
            created_at=sample_created_at
        )

        assert notification.notification_id == sample_notification_id
        assert notification.user_id == sample_user_id
        assert notification.notification_type == NotificationType.FOLLOW
        assert notification.content == sample_content
        assert notification.is_read == False
        assert notification.expires_at == expires_at
        assert notification.created_at == sample_created_at

    def test_create_persistent_notification(self, sample_notification_id, sample_user_id, sample_content, sample_created_at):
        """中期通知の作成テスト"""
        notification = Notification.create_persistent_notification(
            notification_id=sample_notification_id,
            user_id=sample_user_id,
            notification_type=NotificationType.MENTION,
            content=sample_content,
            created_at=sample_created_at
        )

        assert notification.notification_id == sample_notification_id
        assert notification.user_id == sample_user_id
        assert notification.notification_type == NotificationType.MENTION
        assert notification.content == sample_content
        assert notification.is_read == False
        assert notification.expires_at is None
        assert notification.created_at == sample_created_at

    def test_mark_as_read(self, sample_notification_id, sample_user_id, sample_content, sample_created_at):
        """既読にするテスト"""
        notification = Notification(
            notification_id=sample_notification_id,
            user_id=sample_user_id,
            notification_type=NotificationType.LIKE,
            content=sample_content,
            created_at=sample_created_at,
            is_read=False
        )

        assert notification.is_read == False

        notification.mark_as_read()
        assert notification.is_read == True

        # 再度マークしても変わらない
        notification.mark_as_read()
        assert notification.is_read == True

    def test_mark_as_unread(self, sample_notification_id, sample_user_id, sample_content, sample_created_at):
        """未読にするテスト"""
        notification = Notification(
            notification_id=sample_notification_id,
            user_id=sample_user_id,
            notification_type=NotificationType.REPLY,
            content=sample_content,
            created_at=sample_created_at,
            is_read=True
        )

        assert notification.is_read == True

        notification.mark_as_unread()
        assert notification.is_read == False

        # 再度マークしても変わらない
        notification.mark_as_unread()
        assert notification.is_read == False

    def test_is_expired_push_notification(self, sample_notification_id, sample_user_id, sample_content, sample_created_at):
        """プッシュ通知の有効期限テスト"""
        past_time = sample_created_at - timedelta(hours=1)
        future_time = sample_created_at + timedelta(hours=1)

        notification = Notification(
            notification_id=sample_notification_id,
            user_id=sample_user_id,
            notification_type=NotificationType.FOLLOW,
            content=sample_content,
            created_at=sample_created_at,
            expires_at=past_time
        )

        # 期限切れ
        assert notification.is_expired(sample_created_at) == True

        # 有効
        notification_future = Notification(
            notification_id=sample_notification_id,
            user_id=sample_user_id,
            notification_type=NotificationType.FOLLOW,
            content=sample_content,
            created_at=sample_created_at,
            expires_at=future_time
        )
        assert notification_future.is_expired(sample_created_at) == False

    def test_is_expired_persistent_notification(self, sample_notification_id, sample_user_id, sample_content, sample_created_at):
        """中期通知は期限切れにならないテスト"""
        notification = Notification(
            notification_id=sample_notification_id,
            user_id=sample_user_id,
            notification_type=NotificationType.SUBSCRIBE,
            content=sample_content,
            created_at=sample_created_at,
            expires_at=None
        )

        # 中期通知は常に有効
        past_time = sample_created_at - timedelta(days=365)
        assert notification.is_expired(past_time) == False

    def test_properties(self, sample_notification_id, sample_user_id, sample_content, sample_created_at):
        """プロパティのテスト"""
        expires_at = sample_created_at + timedelta(minutes=30)

        notification = Notification(
            notification_id=sample_notification_id,
            user_id=sample_user_id,
            notification_type=NotificationType.LIKE,
            content=sample_content,
            created_at=sample_created_at,
            is_read=True,
            expires_at=expires_at
        )

        assert notification.notification_id == sample_notification_id
        assert notification.user_id == sample_user_id
        assert notification.notification_type == NotificationType.LIKE
        assert notification.content == sample_content
        assert notification.created_at == sample_created_at
        assert notification.is_read == True
        assert notification.expires_at == expires_at
