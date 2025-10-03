import pytest
from src.domain.sns.value_object.notification_id import NotificationId
from src.domain.sns.exception import NotificationIdValidationException


class TestNotificationId:
    """NotificationId値オブジェクトのテスト"""

    def test_create_valid_notification_id(self):
        """有効な通知IDの作成"""
        notification_id = NotificationId(1)
        assert notification_id.value == 1
        assert int(notification_id) == 1
        assert str(notification_id) == "1"

    def test_create_notification_id_from_string(self):
        """文字列からの通知ID作成"""
        notification_id = NotificationId.create("123")
        assert notification_id.value == 123

    def test_create_notification_id_from_int(self):
        """intからの通知ID作成"""
        notification_id = NotificationId.create(456)
        assert notification_id.value == 456

    def test_invalid_notification_id_zero(self):
        """無効な通知ID（0）"""
        with pytest.raises(NotificationIdValidationException, match="通知IDは正の数値である必要があります"):
            NotificationId(0)

    def test_invalid_notification_id_negative(self):
        """無効な通知ID（負の値）"""
        with pytest.raises(NotificationIdValidationException, match="通知IDは正の数値である必要があります"):
            NotificationId(-1)

    def test_invalid_string_notification_id(self):
        """無効な文字列からの通知ID作成"""
        with pytest.raises(NotificationIdValidationException, match="通知IDは正の数値である必要があります"):
            NotificationId.create("invalid")

    def test_invalid_zero_string_notification_id(self):
        """無効な文字列（0）からの通知ID作成"""
        with pytest.raises(NotificationIdValidationException, match="通知IDは正の数値である必要があります"):
            NotificationId.create("0")

    def test_equality(self):
        """等価性のテスト"""
        id1 = NotificationId(1)
        id2 = NotificationId(1)
        id3 = NotificationId(2)

        assert id1 == id2
        assert id1 != id3
        assert id1 != "1"  # 異なる型とは等しくない

    def test_hash(self):
        """ハッシュのテスト"""
        id1 = NotificationId(1)
        id2 = NotificationId(1)

        assert hash(id1) == hash(id2)

        # setで使用可能
        id_set = {id1, id2}
        assert len(id_set) == 1
