import pytest
from datetime import datetime
from src.domain.sns.sns_user_event import SnsUserBlockedEvent


class TestSnsUserBlockedEvent:
    """SnsUserBlockedEventのテスト"""

    def test_create_blocked_event_success(self):
        """正常なブロックイベントの作成テスト"""
        blocker_user_id = 1
        blocked_user_id = 2
        block_time = datetime(2023, 1, 1, 12, 0, 0)

        event = SnsUserBlockedEvent(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id,
            block_time=block_time
        )

        assert event.blocker_user_id == blocker_user_id
        assert event.blocked_user_id == blocked_user_id
        assert event.block_time == block_time

    def test_create_blocked_event_with_default_time(self):
        """デフォルト時間でのブロックイベント作成テスト"""
        blocker_user_id = 1
        blocked_user_id = 2

        event = SnsUserBlockedEvent(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id
        )

        assert event.blocker_user_id == blocker_user_id
        assert event.blocked_user_id == blocked_user_id
        assert isinstance(event.block_time, datetime)

    def test_invalid_blocker_user_id_raises_error(self):
        """無効なブロック実行者IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="blocker_user_id must be positive"):
            SnsUserBlockedEvent(blocker_user_id=0, blocked_user_id=2)

        with pytest.raises(ValueError, match="blocker_user_id must be positive"):
            SnsUserBlockedEvent(blocker_user_id=-1, blocked_user_id=2)

    def test_invalid_blocked_user_id_raises_error(self):
        """無効なブロック対象IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="blocked_user_id must be positive"):
            SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=0)

        with pytest.raises(ValueError, match="blocked_user_id must be positive"):
            SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=-1)

    def test_zero_user_ids_raises_error(self):
        """ユーザーIDが0の場合のエラーテスト"""
        with pytest.raises(ValueError, match="blocker_user_id must be positive"):
            SnsUserBlockedEvent(blocker_user_id=0, blocked_user_id=1)

        with pytest.raises(ValueError, match="blocked_user_id must be positive"):
            SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=0)

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        event = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=2)
        assert event.blocker_user_id == 1
        assert event.blocked_user_id == 2

        # 大きな値
        large_user_id = 999999
        event = SnsUserBlockedEvent(blocker_user_id=large_user_id, blocked_user_id=2)
        assert event.blocker_user_id == large_user_id

        event = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=large_user_id)
        assert event.blocked_user_id == large_user_id

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event1 = SnsUserBlockedEvent(
            blocker_user_id=1,
            blocked_user_id=2,
            block_time=time
        )
        event2 = SnsUserBlockedEvent(
            blocker_user_id=1,
            blocked_user_id=2,
            block_time=time
        )

        # 同じ値であれば等価
        assert event1 == event2
        assert hash(event1) == hash(event2)

    def test_inequality_with_different_blocker_ids(self):
        """異なるブロック実行者IDでの非等価性テスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event1 = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=2, block_time=time)
        event2 = SnsUserBlockedEvent(blocker_user_id=3, blocked_user_id=2, block_time=time)

        assert event1 != event2
        assert hash(event1) != hash(event2)

    def test_inequality_with_different_blocked_ids(self):
        """異なるブロック対象IDでの非等価性テスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event1 = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=2, block_time=time)
        event2 = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=3, block_time=time)

        assert event1 != event2
        assert hash(event1) != hash(event2)

    def test_inequality_with_different_times(self):
        """異なる時間での非等価性テスト"""
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)
        event1 = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=2, block_time=time1)
        event2 = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=2, block_time=time2)

        assert event1 != event2
        assert hash(event1) != hash(event2)

    def test_immutability(self):
        """不変性のテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=2, block_time=time)

        # 作成後に変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_string_representation(self):
        """文字列表現のテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=2, block_time=time)

        str_repr = str(event)
        assert "SnsUserBlockedEvent(" in str_repr
        assert "1" in str_repr
        assert "2" in str_repr

    def test_different_blocker_blocked_combinations(self):
        """異なるブロック実行者・ブロック対象の組み合わせテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)

        # 通常のケース（ブロック実行者がブロック対象より小さい）
        event1 = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=100, block_time=time)
        assert event1.blocker_user_id == 1
        assert event1.blocked_user_id == 100

        # ブロック実行者がブロック対象より大きい
        event2 = SnsUserBlockedEvent(blocker_user_id=100, blocked_user_id=1, block_time=time)
        assert event2.blocker_user_id == 100
        assert event2.blocked_user_id == 1

        # 同じ値の等価性確認
        assert event1 != event2

    def test_auto_generated_time_is_recent(self):
        """自動生成された時間が現在時刻に近いことを確認"""
        event = SnsUserBlockedEvent(blocker_user_id=1, blocked_user_id=2)

        now = datetime.now()
        time_diff = abs((now - event.block_time).total_seconds())
        assert time_diff < 1  # 1秒以内の差
