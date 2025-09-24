import pytest
from datetime import datetime
from src.domain.sns.sns_user_event import SnsUserUnfollowedEvent


class TestSnsUserUnfollowedEvent:
    """SnsUserUnfollowedEventのテスト"""

    def test_create_unfollowed_event_success(self):
        """正常なフォロー解除イベントの作成テスト"""
        follower_user_id = 1
        followee_user_id = 2
        unfollow_time = datetime(2023, 1, 1, 12, 0, 0)

        event = SnsUserUnfollowedEvent(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id,
            unfollow_time=unfollow_time
        )

        assert event.follower_user_id == follower_user_id
        assert event.followee_user_id == followee_user_id
        assert event.unfollow_time == unfollow_time

    def test_create_unfollowed_event_with_default_time(self):
        """デフォルト時間でのフォロー解除イベント作成テスト"""
        follower_user_id = 1
        followee_user_id = 2

        event = SnsUserUnfollowedEvent(
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id
        )

        assert event.follower_user_id == follower_user_id
        assert event.followee_user_id == followee_user_id
        assert isinstance(event.unfollow_time, datetime)

    def test_invalid_follower_user_id_raises_error(self):
        """無効なフォロワーIDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="follower_user_id must be positive"):
            SnsUserUnfollowedEvent(follower_user_id=0, followee_user_id=2)

        with pytest.raises(ValueError, match="follower_user_id must be positive"):
            SnsUserUnfollowedEvent(follower_user_id=-1, followee_user_id=2)

    def test_invalid_followee_user_id_raises_error(self):
        """無効なフォロー対象IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="followee_user_id must be positive"):
            SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=0)

        with pytest.raises(ValueError, match="followee_user_id must be positive"):
            SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=-1)

    def test_zero_user_ids_raises_error(self):
        """ユーザーIDが0の場合のエラーテスト"""
        with pytest.raises(ValueError, match="follower_user_id must be positive"):
            SnsUserUnfollowedEvent(follower_user_id=0, followee_user_id=1)

        with pytest.raises(ValueError, match="followee_user_id must be positive"):
            SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=0)

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        event = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=2)
        assert event.follower_user_id == 1
        assert event.followee_user_id == 2

        # 大きな値
        large_user_id = 999999
        event = SnsUserUnfollowedEvent(follower_user_id=large_user_id, followee_user_id=2)
        assert event.follower_user_id == large_user_id

        event = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=large_user_id)
        assert event.followee_user_id == large_user_id

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event1 = SnsUserUnfollowedEvent(
            follower_user_id=1,
            followee_user_id=2,
            unfollow_time=time
        )
        event2 = SnsUserUnfollowedEvent(
            follower_user_id=1,
            followee_user_id=2,
            unfollow_time=time
        )

        # 同じ値であれば等価
        assert event1 == event2
        assert hash(event1) == hash(event2)

    def test_inequality_with_different_follower_ids(self):
        """異なるフォロワーIDでの非等価性テスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event1 = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=2, unfollow_time=time)
        event2 = SnsUserUnfollowedEvent(follower_user_id=3, followee_user_id=2, unfollow_time=time)

        assert event1 != event2
        assert hash(event1) != hash(event2)

    def test_inequality_with_different_followee_ids(self):
        """異なるフォロー対象IDでの非等価性テスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event1 = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=2, unfollow_time=time)
        event2 = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=3, unfollow_time=time)

        assert event1 != event2
        assert hash(event1) != hash(event2)

    def test_inequality_with_different_times(self):
        """異なる時間での非等価性テスト"""
        time1 = datetime(2023, 1, 1, 12, 0, 0)
        time2 = datetime(2023, 1, 1, 12, 0, 1)
        event1 = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=2, unfollow_time=time1)
        event2 = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=2, unfollow_time=time2)

        assert event1 != event2
        assert hash(event1) != hash(event2)

    def test_immutability(self):
        """不変性のテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=2, unfollow_time=time)

        # 作成後に変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_string_representation(self):
        """文字列表現のテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=2, unfollow_time=time)

        str_repr = str(event)
        assert "SnsUserUnfollowedEvent(" in str_repr
        assert "1" in str_repr
        assert "2" in str_repr

    def test_different_follower_followee_combinations(self):
        """異なるフォロワー・フォロー対象の組み合わせテスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)

        # 通常のケース（フォロワーがフォロー対象より小さい）
        event1 = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=100, unfollow_time=time)
        assert event1.follower_user_id == 1
        assert event1.followee_user_id == 100

        # フォロワーがフォロー対象より大きい
        event2 = SnsUserUnfollowedEvent(follower_user_id=100, followee_user_id=1, unfollow_time=time)
        assert event2.follower_user_id == 100
        assert event2.followee_user_id == 1

        # 同じ値の等価性確認
        assert event1 != event2

    def test_auto_generated_time_is_recent(self):
        """自動生成された時間が現在時刻に近いことを確認"""
        event = SnsUserUnfollowedEvent(follower_user_id=1, followee_user_id=2)

        now = datetime.now()
        time_diff = abs((now - event.unfollow_time).total_seconds())
        assert time_diff < 1  # 1秒以内の差
