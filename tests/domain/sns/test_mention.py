import pytest
from src.domain.sns.mention import Mention


class TestMention:
    """Mentionバリューオブジェクトのテスト"""

    def test_create_mention_success(self):
        """正常なMentionの作成テスト"""
        mentioned_user_name = "testuser"
        post_id = 1

        mention = Mention(mentioned_user_name, post_id)

        assert mention.mentioned_user_name == mentioned_user_name
        assert mention.post_id == post_id

    def test_invalid_post_id_raises_error(self):
        """無効な投稿IDの場合のエラーテスト"""
        with pytest.raises(ValueError, match="post_id must be positive"):
            Mention("testuser", 0)

        with pytest.raises(ValueError, match="post_id must be positive"):
            Mention("testuser", -1)

    def test_none_mentioned_user_name_raises_error(self):
        """mentioned_user_nameがNoneの場合のエラーテスト"""
        with pytest.raises(ValueError, match="mentioned_user_name must be positive"):
            Mention(None, 1)

    def test_empty_mentioned_user_name_raises_error(self):
        """mentioned_user_nameが空文字の場合のエラーテスト"""
        with pytest.raises(ValueError, match="mentioned_user_name must be positive"):
            Mention("", 1)

    def test_boundary_post_id_values(self):
        """境界値の投稿IDテスト"""
        # 最小値（1）
        mention = Mention("testuser", 1)
        assert mention.post_id == 1

        # 大きな値
        large_post_id = 999999
        mention = Mention("testuser", large_post_id)
        assert mention.post_id == large_post_id

    def test_various_mentioned_user_names(self):
        """様々なユーザー名のテスト"""
        # 通常のユーザー名
        mention1 = Mention("testuser", 1)
        assert mention1.mentioned_user_name == "testuser"

        # 長いユーザー名
        long_username = "a" * 50
        mention2 = Mention(long_username, 1)
        assert mention2.mentioned_user_name == long_username

        # 特殊文字を含むユーザー名
        special_username = "test_user-123"
        mention3 = Mention(special_username, 1)
        assert mention3.mentioned_user_name == special_username

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        mention1 = Mention("testuser", 1)
        mention2 = Mention("testuser", 1)

        # 同じユーザー名と投稿IDであれば等価
        assert mention1 == mention2
        assert hash(mention1) == hash(mention2)

    def test_inequality_with_different_mentioned_user_names(self):
        """異なるユーザー名での非等価性テスト"""
        mention1 = Mention("testuser1", 1)
        mention2 = Mention("testuser2", 1)

        assert mention1 != mention2
        assert hash(mention1) != hash(mention2)

    def test_inequality_with_different_post_ids(self):
        """異なる投稿IDでの非等価性テスト"""
        mention1 = Mention("testuser", 1)
        mention2 = Mention("testuser", 2)

        assert mention1 != mention2
        assert hash(mention1) != hash(mention2)

    def test_immutability(self):
        """不変性のテスト"""
        mentioned_user_name = "testuser"
        post_id = 1
        mention = Mention(mentioned_user_name, post_id)

        # 作成後に変更しようとしても変更されない（frozen=Trueによる不変性）

    def test_hash_functionality(self):
        """ハッシュ機能の包括的テスト"""
        # 同じ値のMentionは同じハッシュ値を持つ
        mention1 = Mention("testuser", 1)
        mention2 = Mention("testuser", 1)
        assert hash(mention1) == hash(mention2)

        # ユーザー名が異なる場合は異なるハッシュ値
        mention3 = Mention("otheruser", 1)
        assert hash(mention1) != hash(mention3)

        # 投稿IDが異なる場合は異なるハッシュ値
        mention4 = Mention("testuser", 2)
        assert hash(mention1) != hash(mention4)

    def test_string_representation(self):
        """文字列表現のテスト"""
        mention = Mention("testuser", 1)

        str_repr = str(mention)
        assert "Mention(" in str_repr
        assert "testuser" in str_repr
        assert "1" in str_repr

    def test_edge_cases_for_mentioned_user_name(self):
        """ユーザー名のエッジケーステスト"""
        # スペースを含むユーザー名
        mention1 = Mention("test user", 1)
        assert mention1.mentioned_user_name == "test user"

        # 数字のみのユーザー名
        mention2 = Mention("12345", 1)
        assert mention2.mentioned_user_name == "12345"

        # 記号を含むユーザー名
        mention3 = Mention("test@user", 1)
        assert mention3.mentioned_user_name == "test@user"
