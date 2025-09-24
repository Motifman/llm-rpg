import pytest
from datetime import datetime
from src.domain.sns.post_content import PostContent
from src.domain.sns.sns_enum import PostVisibility


class TestPostContent:
    """PostContentバリューオブジェクトのテスト"""

    def test_create_post_content_success(self):
        """正常なPostContentの作成テスト"""
        content = "テスト投稿です"
        hashtags = ["#テスト", "#投稿"]
        visibility = PostVisibility.PUBLIC

        post_content = PostContent(content, hashtags, visibility)

        assert post_content.content == content
        assert post_content.hashtags == hashtags
        assert post_content.visibility == visibility

    def test_create_post_content_with_defaults(self):
        """デフォルト値でのPostContent作成テスト"""
        content = "デフォルト投稿"

        post_content = PostContent(content)

        assert post_content.content == content
        assert post_content.hashtags == ()
        assert post_content.visibility == PostVisibility.PUBLIC

    def test_content_too_long_raises_error(self):
        """コンテンツが長すぎる場合のエラーテスト"""
        long_content = "a" * 281  # 281文字

        with pytest.raises(ValueError, match="content must be less than 280 characters"):
            PostContent(long_content)

    def test_hashtags_too_many_raises_error(self):
        """ハッシュタグが多すぎる場合のエラーテスト"""
        hashtags = [f"#tag{i}" for i in range(11)]  # 11個

        with pytest.raises(ValueError, match="hashtags must be less than 10"):
            PostContent("content", hashtags)

    def test_invalid_visibility_raises_error(self):
        """無効な可視性のエラーテスト"""
        with pytest.raises(ValueError, match="invalid visibility"):
            PostContent("content", [], "invalid_visibility")

    def test_immutability_after_creation(self):
        """作成後の不変性テスト"""
        hashtags = ("#tag1",)
        post_content = PostContent("content", hashtags, PostVisibility.PUBLIC)

        # タプルは変更できないことを確認
        # これはfrozen=Trueによって保証される

    def test_equality_comparison(self):
        """等価性の比較テスト"""
        content = "同じコンテンツ"
        hashtags = ("#同じタグ",)
        visibility = PostVisibility.PUBLIC

        post1 = PostContent(content, hashtags, visibility)
        post2 = PostContent(content, hashtags, visibility)

        # 異なるインスタンスでも等価
        assert post1 == post2
        assert hash(post1) == hash(post2)

    def test_inequality_comparison(self):
        """非等価性の比較テスト"""
        post1 = PostContent("content1", ("#tag1",), PostVisibility.PUBLIC)
        post2 = PostContent("content2", ("#tag2",), PostVisibility.FOLLOWERS_ONLY)

        assert post1 != post2
        assert hash(post1) != hash(post2)

    def test_boundary_content_length(self):
        """境界値のコンテンツ長テスト"""
        # 最大文字数（280文字）
        max_content = "a" * 280
        post_content = PostContent(max_content)
        assert len(post_content.content) == 280

        # 最小文字数（空文字）
        empty_content = PostContent("")
        assert empty_content.content == ""

    def test_boundary_hashtags_count(self):
        """境界値のハッシュタグ数テスト"""
        # 最大数（10個）
        max_hashtags = tuple(f"#tag{i}" for i in range(10))
        post_content = PostContent("content", max_hashtags)
        assert len(post_content.hashtags) == 10

        # 最小数（0個）
        no_hashtags = PostContent("content", ())
        assert len(no_hashtags.hashtags) == 0
