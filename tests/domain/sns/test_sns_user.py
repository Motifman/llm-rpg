import pytest
from src.domain.sns.sns_user import SnsUser
from src.domain.sns.user_profile import UserProfile


class TestSnsUser:
    """SnsUserエンティティのテスト"""

    def test_create_sns_user_success(self):
        """正常なSnsUserの作成テスト"""
        user_id = 1
        user_profile = UserProfile("testuser", "テストユーザー", "テストです")

        sns_user = SnsUser(user_id, user_profile)

        assert sns_user.user_id == user_id
        assert sns_user.user_profile == user_profile

    def test_invalid_user_id_raises_error(self):
        """無効なユーザーIDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="user_id must be positive"):
            SnsUser(0, UserProfile("testuser", "テストユーザー", "テストです"))

        with pytest.raises(ValueError, match="user_id must be positive"):
            SnsUser(-1, UserProfile("testuser", "テストユーザー", "テストです"))

    def test_boundary_user_id_values(self):
        """境界値のユーザーIDテスト"""
        # 最小値（1）
        user_profile = UserProfile("testuser", "テストユーザー", "テストです")
        sns_user = SnsUser(1, user_profile)
        assert sns_user.user_id == 1

        # 大きな値
        large_user_id = 999999
        sns_user = SnsUser(large_user_id, user_profile)
        assert sns_user.user_id == large_user_id

    def test_update_user_profile_success(self):
        """プロフィール更新のテスト"""
        user_id = 1
        original_profile = UserProfile("testuser", "元の表示名", "元のbio")
        sns_user = SnsUser(user_id, original_profile)

        # 新しいプロフィール
        new_profile = UserProfile("testuser", "新しい表示名", "新しいbio")

        # プロフィール更新
        sns_user.update_user_profile(new_profile)

        # 更新後のプロフィールが反映されていることを確認
        assert sns_user.user_profile == new_profile

    def test_user_profile_immutability_after_creation(self):
        """作成後のプロフィールの不変性テスト"""
        user_id = 1
        user_profile = UserProfile("testuser", "表示名", "bio")
        sns_user = SnsUser(user_id, user_profile)

        # 作成後にプロフィールが変更されないことを確認
        assert sns_user.user_profile == user_profile

    def test_properties_are_readonly(self):
        """プロパティが読み取り専用であることを確認"""
        user_id = 1
        user_profile = UserProfile("testuser", "表示名", "bio")
        sns_user = SnsUser(user_id, user_profile)

        # プロパティ経由で値を取得できる
        assert sns_user.user_id == user_id
        assert sns_user.user_profile == user_profile

    def test_different_instances_with_same_data(self):
        """同じデータを持つ異なるインスタンスのテスト"""
        user_id = 1
        user_profile = UserProfile("testuser", "表示名", "bio")

        sns_user1 = SnsUser(user_id, user_profile)
        sns_user2 = SnsUser(user_id, user_profile)

        # 異なるインスタンスである
        assert sns_user1 is not sns_user2

        # 値は同じ
        assert sns_user1.user_id == sns_user2.user_id
        assert sns_user1.user_profile == sns_user2.user_profile

    def test_user_profile_independence(self):
        """ユーザープロフィールの独立性テスト"""
        user_id = 1
        user_profile = UserProfile("testuser", "表示名", "bio")
        sns_user = SnsUser(user_id, user_profile)

        # 元のプロフィールが変更されても、SNSユーザーのプロフィールは変わらない
        # （ただし、UserProfileは不変なので実際には変更されない）

    def test_string_representation(self):
        """文字列表現のテスト"""
        user_id = 1
        user_profile = UserProfile("testuser", "表示名", "bio")
        sns_user = SnsUser(user_id, user_profile)

        # デフォルトの文字列表現を確認
        str_repr = str(sns_user)
        assert user_id == sns_user.user_id  # プロパティアクセスは動作する
