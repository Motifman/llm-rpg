import pytest
from src.domain.sns.user_profile import UserProfile


class TestUserProfile:
    """UserProfileバリューオブジェクトのテスト"""

    def test_create_user_profile_success(self):
        """正常なUserProfileの作成テスト"""
        user_name = "testuser"
        display_name = "テストユーザー"
        bio = "テストユーザーです"

        profile = UserProfile(user_name, display_name, bio)

        assert profile.user_name == user_name
        assert profile.display_name == display_name
        assert profile.bio == bio

    def test_user_name_too_short_raises_error(self):
        """ユーザー名が短すぎる場合のエラーテスト"""
        with pytest.raises(ValueError, match="ユーザー名は3-20文字である必要があります"):
            UserProfile("ab", "表示名", "bio")

    def test_user_name_too_long_raises_error(self):
        """ユーザー名が長すぎる場合のエラーテスト"""
        long_user_name = "a" * 21  # 21文字
        with pytest.raises(ValueError, match="ユーザー名は3-20文字である必要があります"):
            UserProfile(long_user_name, "表示名", "bio")

    def test_display_name_too_short_raises_error(self):
        """表示名が短すぎる場合のエラーテスト"""
        with pytest.raises(ValueError, match="表示名は1-30文字である必要があります"):
            UserProfile("testuser", "", "bio")

    def test_display_name_too_long_raises_error(self):
        """表示名が長すぎる場合のエラーテスト"""
        long_display_name = "a" * 31  # 31文字
        with pytest.raises(ValueError, match="表示名は1-30文字である必要があります"):
            UserProfile("testuser", long_display_name, "bio")

    def test_bio_too_long_raises_error(self):
        """Bioが長すぎる場合のエラーテスト"""
        long_bio = "a" * 201  # 201文字
        with pytest.raises(ValueError, match="Bioは200文字以内である必要があります"):
            UserProfile("testuser", "表示名", long_bio)

    def test_boundary_user_name_length(self):
        """境界値のユーザー名長テスト"""
        # 最小文字数（3文字）
        min_user_name = "abc"
        profile = UserProfile(min_user_name, "表示名", "bio")
        assert profile.user_name == min_user_name

        # 最大文字数（20文字）
        max_user_name = "a" * 20
        profile = UserProfile(max_user_name, "表示名", "bio")
        assert profile.user_name == max_user_name

    def test_boundary_display_name_length(self):
        """境界値の表示名長テスト"""
        # 最小文字数（1文字）
        min_display_name = "a"
        profile = UserProfile("testuser", min_display_name, "bio")
        assert profile.display_name == min_display_name

        # 最大文字数（30文字）
        max_display_name = "a" * 30
        profile = UserProfile("testuser", max_display_name, "bio")
        assert profile.display_name == max_display_name

    def test_boundary_bio_length(self):
        """境界値のBio長テスト"""
        # 最大文字数（200文字）
        max_bio = "a" * 200
        profile = UserProfile("testuser", "表示名", max_bio)
        assert profile.bio == max_bio

        # 最小文字数（空文字）
        empty_bio = UserProfile("testuser", "表示名", "")
        assert empty_bio.bio == ""

    def test_update_bio_returns_new_instance(self):
        """update_bioが新しいインスタンスを返すテスト"""
        original_profile = UserProfile("testuser", "表示名", "元のbio")
        new_bio = "新しいbio"

        updated_profile = original_profile.update_bio(new_bio)

        # 新しいインスタンスが作成される
        assert updated_profile.bio == new_bio
        assert updated_profile.user_name == original_profile.user_name
        assert updated_profile.display_name == original_profile.display_name

        # 元のインスタンスは変更されない
        assert original_profile.bio == "元のbio"

    def test_update_display_name_returns_new_instance(self):
        """update_display_nameが新しいインスタンスを返すテスト"""
        original_profile = UserProfile("testuser", "元の表示名", "bio")
        new_display_name = "新しい表示名"

        updated_profile = original_profile.update_display_name(new_display_name)

        # 新しいインスタンスが作成される
        assert updated_profile.display_name == new_display_name
        assert updated_profile.user_name == original_profile.user_name
        assert updated_profile.bio == original_profile.bio

        # 元のインスタンスは変更されない
        assert original_profile.display_name == "元の表示名"

    def test_immutability_after_update(self):
        """更新後の不変性テスト"""
        profile = UserProfile("testuser", "表示名", "bio")
        new_profile = profile.update_bio("新しいbio")

        # 異なるインスタンスであることを確認
        assert profile != new_profile
        assert profile is not new_profile

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        profile1 = UserProfile("testuser", "表示名", "bio")
        profile2 = UserProfile("testuser", "表示名", "bio")

        # 異なるインスタンスでも等価
        assert profile1 == profile2
        assert hash(profile1) == hash(profile2)

    def test_inequality_comparison(self):
        """非等価性の比較テスト"""
        profile1 = UserProfile("testuser1", "表示名1", "bio1")
        profile2 = UserProfile("testuser2", "表示名2", "bio2")

        assert profile1 != profile2
        assert hash(profile1) != hash(profile2)
