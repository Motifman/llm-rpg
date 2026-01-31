import pytest
from datetime import datetime
from ai_rpg_world.domain.sns.value_object import PostContent
from ai_rpg_world.domain.sns.enum import PostVisibility
from ai_rpg_world.domain.sns.exception import ContentLengthValidationException, HashtagCountValidationException, VisibilityValidationException


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

        with pytest.raises(ContentLengthValidationException, match="コンテンツは280文字以内でなければなりません"):
            PostContent(long_content)

    def test_hashtags_too_many_raises_error(self):
        """ハッシュタグが多すぎる場合のエラーテスト"""
        hashtags = [f"#tag{i}" for i in range(11)]  # 11個

        with pytest.raises(HashtagCountValidationException, match="ハッシュタグは10個以内でなければなりません"):
            PostContent("content", hashtags)

    def test_invalid_visibility_raises_error(self):
        """無効な可視性のエラーテスト"""
        with pytest.raises(VisibilityValidationException, match="可視性は有効な値である必要があります"):
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

    def test_create_method_with_hashtag_extraction(self):
        """createメソッドでのハッシュタグ自動抽出テスト"""
        content = "今日は良い天気です #weather #sunny #happy"
        visibility = PostVisibility.PUBLIC

        post_content = PostContent.create(content, visibility)

        assert post_content.content == content
        assert post_content.visibility == visibility
        assert post_content.hashtags == ("weather", "sunny", "happy")

    def test_create_method_no_hashtags(self):
        """createメソッドでハッシュタグなしのテスト"""
        content = "ハッシュタグのない普通の投稿です"
        visibility = PostVisibility.FOLLOWERS_ONLY

        post_content = PostContent.create(content, visibility)

        assert post_content.content == content
        assert post_content.visibility == visibility
        assert post_content.hashtags == ()

    def test_create_method_special_hashtag_patterns(self):
        """createメソッドでの特殊なハッシュタグパターン抽出テスト"""
        content = "テスト #tag1 #tag-2 #tag_3 #tag.with.dots #123invalid"
        visibility = PostVisibility.PRIVATE

        post_content = PostContent.create(content, visibility)

        assert post_content.content == content
        assert post_content.visibility == visibility
        # 正規表現(\w+)は英数字とアンダースコアのみなので、ハイフンやドットは区切り文字になる
        assert post_content.hashtags == ("tag1", "tag", "tag_3", "tag", "123invalid")

    def test_create_method_with_default_visibility(self):
        """createメソッドでのデフォルト可視性テスト"""
        content = "デフォルト可視性のテスト #default"

        post_content = PostContent.create(content)

        assert post_content.content == content
        assert post_content.visibility == PostVisibility.PUBLIC
        assert post_content.hashtags == ("default",)
