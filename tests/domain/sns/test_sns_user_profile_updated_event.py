import pytest
from datetime import datetime
from src.domain.sns.sns_user_event import SnsUserProfileUpdatedEvent


class TestSnsUserProfileUpdatedEvent:
    """SnsUserProfileUpdatedEventのテスト"""

    def test_create_profile_updated_event_success(self):
        """正常なプロフィール更新イベントの作成テスト"""
        user_id = 1
        new_bio = "新しいbio"
        new_display_name = "新しい表示名"
        updated_time = datetime(2023, 1, 1, 12, 0, 0)

        event = SnsUserProfileUpdatedEvent(
            user_id=user_id,
            new_bio=new_bio,
            new_display_name=new_display_name,
            updated_time=updated_time
        )

        assert event.user_id == user_id
        assert event.new_bio == new_bio
        assert event.new_display_name == new_display_name
        assert event.updated_time == updated_time

    def test_create_profile_updated_event_with_default_time(self):
        """デフォルト時間でのプロフィール更新イベント作成テスト"""
        user_id = 1
        new_bio = "新しいbio"
        new_display_name = "新しい表示名"

        event = SnsUserProfileUpdatedEvent(
            user_id=user_id,
            new_bio=new_bio,
            new_display_name=new_display_name
        )

        assert event.user_id == user_id
        assert event.new_bio == new_bio
        assert event.new_display_name == new_display_name
        assert isinstance(event.updated_time, datetime)

    def test_invalid_user_id_raises_error(self):
        """無効なユーザーIDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="user_id must be positive"):
            SnsUserProfileUpdatedEvent(user_id=0, new_bio="bio", new_display_name="name")

    def test_bio_too_long_raises_error(self):
        """Bioが長すぎる場合のエラーテスト"""
        long_bio = "a" * 201  # 201文字
        with pytest.raises(ValueError, match="new_bio must be less than 200 characters"):
            SnsUserProfileUpdatedEvent(user_id=1, new_bio=long_bio, new_display_name="name")

    def test_display_name_too_long_raises_error(self):
        """表示名が長すぎる場合のエラーテスト"""
        long_display_name = "a" * 31  # 31文字
        with pytest.raises(ValueError, match="new_display_name must be less than 30 characters"):
            SnsUserProfileUpdatedEvent(user_id=1, new_bio="bio", new_display_name=long_display_name)

    def test_boundary_lengths(self):
        """境界値の長さテスト"""
        # Bioの最大文字数（200文字）
        max_bio = "a" * 200
        event = SnsUserProfileUpdatedEvent(user_id=1, new_bio=max_bio, new_display_name="name")
        assert len(event.new_bio) == 200

        # 表示名の最大文字数（30文字）
        max_display_name = "a" * 30
        event = SnsUserProfileUpdatedEvent(user_id=1, new_bio="bio", new_display_name=max_display_name)
        assert len(event.new_display_name) == 30

        # 最小文字数（空文字）
        event = SnsUserProfileUpdatedEvent(user_id=1, new_bio="", new_display_name="")
        assert event.new_bio == ""
        assert event.new_display_name == ""

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        time = datetime(2023, 1, 1, 12, 0, 0)
        event1 = SnsUserProfileUpdatedEvent(
            user_id=1,
            new_bio="bio",
            new_display_name="name",
            updated_time=time
        )
        event2 = SnsUserProfileUpdatedEvent(
            user_id=1,
            new_bio="bio",
            new_display_name="name",
            updated_time=time
        )
        assert event1 == event2
        assert hash(event1) == hash(event2)

    def test_auto_generated_time_is_recent(self):
        """自動生成された時間が現在時刻に近いことを確認"""
        event = SnsUserProfileUpdatedEvent(user_id=1, new_bio="bio", new_display_name="name")
        now = datetime.now()
        time_diff = abs((now - event.updated_time).total_seconds())
        assert time_diff < 1
