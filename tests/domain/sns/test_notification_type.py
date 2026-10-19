import pytest

from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType


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

    def test_notification_type_membership(self):
        """保存された6種の文字列から正しい通知種別を復元し、未知の文字列を拒む。"""
        for value, expected in [
            ("follow", NotificationType.FOLLOW),
            ("mention", NotificationType.MENTION),
            ("like", NotificationType.LIKE),
            ("reply", NotificationType.REPLY),
            ("subscribe", NotificationType.SUBSCRIBE),
            ("post", NotificationType.POST),
        ]:
            assert NotificationType(value) == expected

        with pytest.raises(ValueError):
            NotificationType("nonexistent")

    def test_notification_type_iteration(self):
        """イテレーション可能"""
        types = list(NotificationType)
        assert len(types) == 6
        assert NotificationType.FOLLOW in types
        assert NotificationType.MENTION in types
        assert NotificationType.POST in types
