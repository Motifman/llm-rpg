import pytest
from datetime import datetime
from src.domain.sns.base_sns_event import SnsUserSubscribedEvent


class TestSnsUserSubscribedEvent:
    """SnsUserSubscribedEventのテスト"""

    def test_create_subscribed_event_success(self):
        """正常な購読イベントの作成テスト"""
        subscriber_user_id = 1
        subscribed_user_id = 2
        created_at = datetime(2023, 1, 1, 12, 0, 0)

        event = SnsUserSubscribedEvent(
            from_user_id=subscriber_user_id,
            to_user_id=subscribed_user_id,
            created_at=created_at
        )

        assert event.from_user_id == subscriber_user_id
        assert event.to_user_id == subscribed_user_id
        assert event.created_at == created_at

    def test_create_subscribed_event_with_default_time(self):
        """デフォルト時間での購読イベント作成テスト"""
        subscriber_user_id = 1
        subscribed_user_id = 2

        event = SnsUserSubscribedEvent(
            from_user_id=subscriber_user_id,
            to_user_id=subscribed_user_id
        )

        assert event.from_user_id == subscriber_user_id
        assert event.to_user_id == subscribed_user_id
        assert isinstance(event.created_at, datetime)

    def test_invalid_from_user_id_raises_error(self):
        """無効な実行者IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="from_user_id must be positive"):
            SnsUserSubscribedEvent(from_user_id=0, to_user_id=2)

    def test_invalid_to_user_id_raises_error(self):
        """無効な対象IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="to_user_id must be positive"):
            SnsUserSubscribedEvent(from_user_id=1, to_user_id=0)

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event1 = SnsUserSubscribedEvent(from_user_id=1, to_user_id=2, created_at=time)
        event2 = SnsUserSubscribedEvent(from_user_id=1, to_user_id=2, created_at=time)
        assert event1 == event2
        assert hash(event1) == hash(event2)

    def test_auto_generated_time_is_recent(self):
        """自動生成された時間が現在時刻に近いことを確認"""
        event = SnsUserSubscribedEvent(from_user_id=1, to_user_id=2)
        now = datetime.now()
        time_diff = abs((now - event.created_at).total_seconds())
        assert time_diff < 1
