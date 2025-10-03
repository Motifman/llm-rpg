import pytest
from src.domain.sns.value_object.notification_type import NotificationType


class TestNotificationType:
    """NotificationType列挙型のテスト"""

    def test_notification_type_values(self):
        """通知タイプの値確認"""
        assert NotificationType.FOLLOW.value == "follow"
        assert NotificationType.MENTION.value == "mention"
        assert NotificationType.LIKE.value == "like"
        assert NotificationType.REPLY.value == "reply"
        assert NotificationType.SUBSCRIBE.value == "subscribe"
        assert NotificationType.POST.value == "post"

    def test_notification_type_string_conversion(self):
        """文字列変換のテスト"""
        assert str(NotificationType.FOLLOW) == "follow"
        assert str(NotificationType.MENTION) == "mention"
        assert str(NotificationType.LIKE) == "like"
        assert str(NotificationType.REPLY) == "reply"
        assert str(NotificationType.SUBSCRIBE) == "subscribe"
        assert str(NotificationType.POST) == "post"

    def test_notification_type_enum_properties(self):
        """Enumの基本プロパティテスト"""
        # すべてのメンバーがNotificationTypeのインスタンスであること
        for notification_type in NotificationType:
            assert isinstance(notification_type, NotificationType)
            assert hasattr(notification_type, 'value')
            assert hasattr(notification_type, 'name')

    def test_notification_type_uniqueness(self):
        """値の一意性確認"""
        values = [nt.value for nt in NotificationType]
        assert len(values) == len(set(values))  # 重複なし

    def test_notification_type_membership(self):
        """メンバーシップテスト"""
        assert NotificationType.FOLLOW in NotificationType
        # 文字列値はEnumメンバーの.valueとして存在することを確認
        assert any(nt.value == "follow" for nt in NotificationType)
        assert not any(nt.value == "nonexistent" for nt in NotificationType)

    def test_notification_type_iteration(self):
        """イテレーション可能"""
        types = list(NotificationType)
        assert len(types) == 6
        assert NotificationType.FOLLOW in types
        assert NotificationType.MENTION in types
        assert NotificationType.POST in types
