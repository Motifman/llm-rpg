import pytest
from datetime import datetime
from game.sns.sns_data import Post
from game.enums import PostVisibility


class TestPostFormatting:
    """Postクラスの整形メソッドのテスト"""
    
    def test_format_post_basic(self):
        """基本的な投稿の整形テスト"""
        post = Post.create(
            user_id="test_user",
            content="これはテスト投稿です。",
            hashtags=["テスト", "投稿"],
            visibility=PostVisibility.PUBLIC
        )
        
        formatted = post.format_post()
        
        assert "📝 test_userの投稿" in formatted
        assert "これはテスト投稿です。" in formatted
        assert "🌍 パブリック" in formatted
        assert "🏷️ #テスト #投稿" in formatted
        assert "📅" in formatted
        assert "=" * 40 in formatted
    
    def test_format_post_with_author_name(self):
        """投稿者名を指定した整形テスト"""
        post = Post.create(
            user_id="test_user",
            content="これはテスト投稿です。",
            visibility=PostVisibility.FOLLOWERS_ONLY
        )
        
        formatted = post.format_post(author_name="テストユーザー")
        
        assert "📝 テストユーザーの投稿" in formatted
        assert "👥 フォロワー限定" in formatted
    
    def test_format_post_without_metadata(self):
        """メタデータなしの整形テスト"""
        post = Post.create(
            user_id="test_user",
            content="これはテスト投稿です。",
            hashtags=["テスト"]
        )
        
        formatted = post.format_post(include_metadata=False)
        
        assert "📝 test_userの投稿" in formatted
        assert "これはテスト投稿です。" in formatted
        assert "🏷️" not in formatted
        assert "🌍 パブリック" not in formatted
        assert "📅" not in formatted
    
    def test_format_post_specified_users(self):
        """指定ユーザー限定投稿の整形テスト"""
        post = Post.create(
            user_id="test_user",
            content="これは限定投稿です。",
            visibility=PostVisibility.SPECIFIED_USERS,
            allowed_users=["user1", "user2", "user3"]
        )
        
        formatted = post.format_post()
        
        assert "🎯 指定ユーザー限定" in formatted
        assert "👥 許可ユーザー: user1, user2, user3" in formatted
    
    def test_format_compact(self):
        """コンパクト形式の整形テスト"""
        post = Post.create(
            user_id="test_user",
            content="これは短い投稿です。",
            visibility=PostVisibility.PRIVATE
        )
        
        formatted = post.format_compact()
        
        assert "📝 test_user: これは短い投稿です。" in formatted
        assert "🔒 プライベート" in formatted
    
    def test_format_compact_long_content(self):
        """長い内容のコンパクト形式テスト"""
        long_content = "これは非常に長い投稿内容です。" * 10
        post = Post.create(
            user_id="test_user",
            content=long_content,
            visibility=PostVisibility.MUTUAL_FOLLOWS_ONLY
        )
        
        formatted = post.format_compact()
        
        # 長い内容が50文字で切り詰められ、"..."が追加されることを確認
        assert "📝 test_user:" in formatted
        assert "..." in formatted
        assert "🤝 相互フォロー限定" in formatted
        # 50文字を超える内容が含まれていないことを確認
        assert len(formatted.split(": ")[1].split(" [")[0]) <= 53  # "..."を含むため53文字以下
    
    def test_format_for_timeline(self):
        """タイムライン形式の整形テスト"""
        post = Post.create(
            user_id="test_user",
            content="これはタイムライン投稿です。",
            hashtags=["タイムライン", "テスト"],
            visibility=PostVisibility.PUBLIC
        )
        
        formatted = post.format_for_timeline()
        
        assert "📝 test_user" in formatted
        assert "これはタイムライン投稿です。" in formatted
        assert "🏷️ #タイムライン #テスト" in formatted
        assert "🌍 パブリック" in formatted
        assert "-" * 30 in formatted
    
    def test_format_for_timeline_with_author_name(self):
        """投稿者名を指定したタイムライン形式テスト"""
        post = Post.create(
            user_id="test_user",
            content="これはタイムライン投稿です。",
            visibility=PostVisibility.FOLLOWERS_ONLY
        )
        
        formatted = post.format_for_timeline(author_name="テストユーザー")
        
        assert "📝 テストユーザー" in formatted
        assert "👥 フォロワー限定" in formatted
    
    def test_edited_post_formatting(self):
        """編集された投稿の整形テスト"""
        # 作成日時と更新日時が異なる投稿を作成
        created_at = datetime(2024, 1, 1, 12, 0, 0)
        updated_at = datetime(2024, 1, 1, 14, 30, 0)
        
        post = Post(
            post_id="test_post",
            user_id="test_user",
            content="これは編集された投稿です。",
            hashtags=[],
            visibility=PostVisibility.PUBLIC,
            allowed_users=[],
            created_at=created_at,
            updated_at=updated_at
        )
        
        formatted = post.format_post()
        
        assert "📅 2024年01月01日 12:00" in formatted
        assert "✏️ 編集: 2024年01月01日 14:30" in formatted
    
    def test_visibility_labels(self):
        """可視性ラベルのテスト"""
        post_public = Post.create("user1", "パブリック投稿", visibility=PostVisibility.PUBLIC)
        post_private = Post.create("user2", "プライベート投稿", visibility=PostVisibility.PRIVATE)
        post_followers = Post.create("user3", "フォロワー限定投稿", visibility=PostVisibility.FOLLOWERS_ONLY)
        post_mutual = Post.create("user4", "相互フォロー限定投稿", visibility=PostVisibility.MUTUAL_FOLLOWS_ONLY)
        post_specified = Post.create("user5", "指定ユーザー限定投稿", visibility=PostVisibility.SPECIFIED_USERS)
        
        assert post_public.get_visibility_label() == "🌍 パブリック"
        assert post_private.get_visibility_label() == "🔒 プライベート"
        assert post_followers.get_visibility_label() == "👥 フォロワー限定"
        assert post_mutual.get_visibility_label() == "🤝 相互フォロー限定"
        assert post_specified.get_visibility_label() == "🎯 指定ユーザー限定" 