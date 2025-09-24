import pytest
from datetime import datetime
from src.domain.sns.sns_user_event import SnsUserUnblockedEvent


class TestSnsUserUnblockedEvent:
    """SnsUserUnblockedEventのテスト"""

    def test_create_unblocked_event_success(self):
        """正常なブロック解除イベントの作成テスト"""
        blocker_user_id = 1
        blocked_user_id = 2
        unblock_time = datetime(2023, 1, 1, 12, 0, 0)

        event = SnsUserUnblockedEvent(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id,
            unblock_time=unblock_time
        )

        assert event.blocker_user_id == blocker_user_id
        assert event.blocked_user_id == blocked_user_id
        assert event.unblock_time == unblock_time

    def test_create_unblocked_event_with_default_time(self):
        """デフォルト時間でのブロック解除イベント作成テスト"""
        blocker_user_id = 1
        blocked_user_id = 2

        event = SnsUserUnblockedEvent(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )

        assert event.blocker_user_id == blocker_user_id
        assert event.blocked_user_id == blocked_user_id
        assert isinstance(event.unblock_time, datetime)

    def test_invalid_blocker_user_id_raises_error(self):
        """無効なブロック実行者IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="blocker_user_id must be positive"):
            SnsUserUnblockedEvent(blocker_user_id=0, blocked_user_id=2)

    def test_invalid_blocked_user_id_raises_error(self):
        """無効なブロック対象IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="blocked_user_id must be positive"):
            SnsUserUnblockedEvent(blocker_user_id=1, blocked_user_id=0)

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event1 = SnsUserUnblockedEvent(blocker_user_id=1, blocked_user_id=2, unblock_time=time)
        event2 = SnsUserUnblockedEvent(blocker_user_id=1, blocked_user_id=2, unblock_time=time)
        assert event1 == event2
        assert hash(event1) == hash(event2)

    def test_auto_generated_time_is_recent(self):
        """自動生成された時間が現在時刻に近いことを確認"""
        event = SnsUserUnblockedEvent(blocker_user_id=1, blocked_user_id=2)
        now = datetime.now()
        time_diff = abs((now - event.unblock_time).total_seconds())
        assert time_diff < 1
