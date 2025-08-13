import pytest
from datetime import datetime, timedelta
from src_old.systems.sns_system import SnsSystem
from src_old.models.sns import SnsUser, Post, Follow, Like, Reply, Notification, NotificationType


class TestSnsSystem:
    """SNSシステムのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.sns = SnsSystem()
        
        # テスト用ユーザーを作成
        self.user1 = self.sns.create_user("user1", "アリス", "よろしくお願いします")
        self.user2 = self.sns.create_user("user2", "ボブ", "エンジニアです")
        self.user3 = self.sns.create_user("user3", "チャーリー", "")
    
    # === ユーザー管理のテスト ===
    
    def test_create_user(self):
        """ユーザー作成のテスト"""
        user = self.sns.create_user("test_user", "テストユーザー", "テスト用アカウント")
        
        assert user.user_id == "test_user"
        assert user.name == "テストユーザー"
        assert user.bio == "テスト用アカウント"
        assert isinstance(user.created_at, datetime)
        assert self.sns.user_exists("test_user")
    
    def test_create_duplicate_user(self):
        """重複ユーザー作成のテスト"""
        with pytest.raises(ValueError, match="ユーザーID 'user1' は既に存在します"):
            self.sns.create_user("user1", "重複ユーザー")
    
    def test_get_user(self):
        """ユーザー取得のテスト"""
        user = self.sns.get_user("user1")
        assert user is not None
        assert user.user_id == "user1"
        assert user.name == "アリス"
        
        # 存在しないユーザー
        assert self.sns.get_user("nonexistent") is None
    
    def test_update_user_bio(self):
        """ユーザープロフィール更新のテスト"""
        updated_user = self.sns.update_user_bio("user1", "新しい一言コメント")
        assert updated_user is not None
        assert updated_user.bio == "新しい一言コメント"
        
        # ストレージからも更新されているかチェック
        stored_user = self.sns.get_user("user1")
        assert stored_user.bio == "新しい一言コメント"
        
        # 存在しないユーザー
        assert self.sns.update_user_bio("nonexistent", "test") is None
    
    # === 投稿機能のテスト ===
    
    def test_create_post(self):
        """投稿作成のテスト"""
        post = self.sns.create_post("user1", "こんにちは、世界！")
        
        assert post is not None
        assert post.user_id == "user1"
        assert post.content == "こんにちは、世界！"
        assert len(post.post_id) > 0
        assert isinstance(post.created_at, datetime)
    
    def test_create_post_with_hashtags(self):
        """ハッシュタグ付き投稿のテスト"""
        post = self.sns.create_post("user1", "今日は良い天気 #天気 #日記", ["#初投稿"])
        
        assert post is not None
        assert "#天気" in post.hashtags
        assert "#日記" in post.hashtags
        assert "#初投稿" in post.hashtags
        assert len(set(post.hashtags)) == len(post.hashtags)  # 重複なし
    
    def test_create_post_nonexistent_user(self):
        """存在しないユーザーの投稿作成テスト"""
        post = self.sns.create_post("nonexistent", "テスト投稿")
        assert post is None
    
    def test_get_user_posts(self):
        """ユーザーの投稿取得のテスト"""
        # 複数の投稿を作成
        post1 = self.sns.create_post("user1", "最初の投稿")
        post2 = self.sns.create_post("user1", "2番目の投稿")
        post3 = self.sns.create_post("user2", "user2の投稿")
        
        user1_posts = self.sns.get_user_posts("user1")
        assert len(user1_posts) == 2
        assert post2 in user1_posts  # 新しい順
        assert post1 in user1_posts
        assert post3 not in user1_posts
    
    # === タイムライン機能のテスト ===
    
    def test_global_timeline(self):
        """グローバルタイムラインのテスト"""
        post1 = self.sns.create_post("user1", "投稿1")
        post2 = self.sns.create_post("user2", "投稿2")
        post3 = self.sns.create_post("user3", "投稿3")
        
        timeline = self.sns.get_global_timeline()
        assert len(timeline) == 3
        assert timeline[0] == post3  # 最新が最初
        assert timeline[1] == post2
        assert timeline[2] == post1
    
    def test_following_timeline(self):
        """フォロー中タイムラインのテスト"""
        # user1がuser2をフォロー
        self.sns.follow_user("user1", "user2")
        
        post1 = self.sns.create_post("user1", "user1の投稿")
        post2 = self.sns.create_post("user2", "user2の投稿")
        post3 = self.sns.create_post("user3", "user3の投稿")
        
        timeline = self.sns.get_following_timeline("user1")
        assert len(timeline) == 1  # user2の投稿のみ
        assert timeline[0] == post2
    
    def test_hashtag_timeline(self):
        """ハッシュタグタイムラインのテスト"""
        post1 = self.sns.create_post("user1", "今日は楽しい #日記")
        post2 = self.sns.create_post("user2", "明日も頑張る #日記 #仕事")
        post3 = self.sns.create_post("user3", "お疲れ様 #仕事")
        
        diary_timeline = self.sns.get_hashtag_timeline("日記")
        assert len(diary_timeline) == 2
        assert post1 in diary_timeline
        assert post2 in diary_timeline
        
        # #記号ありでも正常に動作
        diary_timeline2 = self.sns.get_hashtag_timeline("#日記")
        assert len(diary_timeline2) == 2
    
    # === フォロー機能のテスト ===
    
    def test_follow_user(self):
        """フォロー機能のテスト"""
        result = self.sns.follow_user("user1", "user2")
        assert result is True
        assert self.sns.is_following("user1", "user2")
        
        # 通知が作成されているかチェック
        notifications = self.sns.get_user_notifications("user2")
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.FOLLOW
        assert notifications[0].from_user_id == "user1"
    
    def test_follow_self(self):
        """自分自身をフォローするテスト"""
        result = self.sns.follow_user("user1", "user1")
        assert result is False
    
    def test_follow_nonexistent_user(self):
        """存在しないユーザーをフォローするテスト"""
        result = self.sns.follow_user("user1", "nonexistent")
        assert result is False
    
    def test_duplicate_follow(self):
        """重複フォローのテスト"""
        self.sns.follow_user("user1", "user2")
        result = self.sns.follow_user("user1", "user2")
        assert result is False
    
    def test_unfollow_user(self):
        """フォロー解除のテスト"""
        self.sns.follow_user("user1", "user2")
        assert self.sns.is_following("user1", "user2")
        
        result = self.sns.unfollow_user("user1", "user2")
        assert result is True
        assert not self.sns.is_following("user1", "user2")
    
    def test_follow_counts(self):
        """フォロー数・フォロワー数のテスト"""
        self.sns.follow_user("user1", "user2")
        self.sns.follow_user("user1", "user3")
        self.sns.follow_user("user3", "user2")
        
        # user1のフォロー中
        assert self.sns.get_following_count("user1") == 2
        following_list = self.sns.get_following_list("user1")
        assert "user2" in following_list
        assert "user3" in following_list
        
        # user2のフォロワー
        assert self.sns.get_followers_count("user2") == 2
        followers_list = self.sns.get_followers_list("user2")
        assert "user1" in followers_list
        assert "user3" in followers_list
    
    # === いいね機能のテスト ===
    
    def test_like_post(self):
        """いいね機能のテスト"""
        post = self.sns.create_post("user1", "いいねテスト投稿")
        
        result = self.sns.like_post("user2", post.post_id)
        assert result is True
        assert self.sns.has_liked("user2", post.post_id)
        assert self.sns.get_post_likes_count(post.post_id) == 1
        
        # いいね通知が作成されているかチェック
        notifications = self.sns.get_user_notifications("user1")
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.LIKE
    
    def test_like_own_post(self):
        """自分の投稿にいいねするテスト（通知は作成されない）"""
        post = self.sns.create_post("user1", "自分の投稿")
        
        result = self.sns.like_post("user1", post.post_id)
        assert result is True
        
        # 通知は作成されない
        notifications = self.sns.get_user_notifications("user1")
        assert len(notifications) == 0
    
    def test_duplicate_like(self):
        """重複いいねのテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        
        self.sns.like_post("user2", post.post_id)
        result = self.sns.like_post("user2", post.post_id)
        assert result is False
        assert self.sns.get_post_likes_count(post.post_id) == 1
    
    def test_unlike_post(self):
        """いいね解除のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        
        self.sns.like_post("user2", post.post_id)
        assert self.sns.has_liked("user2", post.post_id)
        
        result = self.sns.unlike_post("user2", post.post_id)
        assert result is True
        assert not self.sns.has_liked("user2", post.post_id)
        assert self.sns.get_post_likes_count(post.post_id) == 0
    
    # === 返信機能のテスト ===
    
    def test_reply_to_post(self):
        """返信機能のテスト"""
        post = self.sns.create_post("user1", "元投稿")
        
        reply = self.sns.reply_to_post("user2", post.post_id, "返信内容")
        assert reply is not None
        assert reply.user_id == "user2"
        assert reply.post_id == post.post_id
        assert reply.content == "返信内容"
        
        # 返信数のチェック
        assert self.sns.get_post_replies_count(post.post_id) == 1
        
        # 返信通知が作成されているかチェック
        notifications = self.sns.get_user_notifications("user1")
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.REPLY
    
    def test_reply_to_own_post(self):
        """自分の投稿に返信するテスト（通知は作成されない）"""
        post = self.sns.create_post("user1", "自分の投稿")
        
        reply = self.sns.reply_to_post("user1", post.post_id, "自分への返信")
        assert reply is not None
        
        # 通知は作成されない
        notifications = self.sns.get_user_notifications("user1")
        assert len(notifications) == 0
    
    def test_get_post_replies(self):
        """投稿の返信取得のテスト"""
        post = self.sns.create_post("user1", "元投稿")
        
        reply1 = self.sns.reply_to_post("user2", post.post_id, "最初の返信")
        reply2 = self.sns.reply_to_post("user3", post.post_id, "2番目の返信")
        
        replies = self.sns.get_post_replies(post.post_id)
        assert len(replies) == 2
        assert reply1 in replies
        assert reply2 in replies
        # 古い順で返される
        assert replies[0] == reply1
        assert replies[1] == reply2
    
    # === 通知機能のテスト ===
    
    def test_notification_creation(self):
        """通知作成のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        
        # フォロー通知
        self.sns.follow_user("user2", "user1")
        
        # いいね通知
        self.sns.like_post("user2", post.post_id)
        
        # 返信通知
        self.sns.reply_to_post("user2", post.post_id, "返信です")
        
        notifications = self.sns.get_user_notifications("user1")
        assert len(notifications) == 3
        
        types = [n.type for n in notifications]
        assert NotificationType.FOLLOW in types
        assert NotificationType.LIKE in types
        assert NotificationType.REPLY in types
    
    def test_unread_notifications(self):
        """未読通知のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        self.sns.like_post("user2", post.post_id)
        
        # 未読通知数
        assert self.sns.get_unread_notifications_count("user1") == 1
        
        # 未読通知のみ取得
        unread_notifications = self.sns.get_user_notifications("user1", unread_only=True)
        assert len(unread_notifications) == 1
        
        # 既読にマーク
        notification_id = unread_notifications[0].notification_id
        result = self.sns.mark_notification_as_read(notification_id)
        assert result is True
        
        # 未読通知数が0になる
        assert self.sns.get_unread_notifications_count("user1") == 0
    
    # === 統計情報のテスト ===
    
    def test_system_stats(self):
        """システム統計情報のテスト"""
        # 初期状態
        stats = self.sns.get_system_stats()
        assert stats["total_users"] == 3  # setup_methodで作成された3ユーザー
        assert stats["total_posts"] == 0
        assert stats["total_follows"] == 0
        assert stats["total_likes"] == 0
        assert stats["total_replies"] == 0
        assert stats["total_notifications"] == 0
        
        # 各種操作を実行
        post = self.sns.create_post("user1", "テスト投稿")
        self.sns.follow_user("user2", "user1")
        self.sns.like_post("user2", post.post_id)
        self.sns.reply_to_post("user2", post.post_id, "返信")
        
        # 統計情報の更新を確認
        stats = self.sns.get_system_stats()
        assert stats["total_users"] == 3
        assert stats["total_posts"] == 1
        assert stats["total_follows"] == 1
        assert stats["total_likes"] == 1
        assert stats["total_replies"] == 1
        assert stats["total_notifications"] == 3  # フォロー、いいね、返信の通知
    
    # === エッジケースのテスト ===
    
    def test_empty_content_post(self):
        """空の内容での投稿テスト"""
        post = self.sns.create_post("user1", "")
        assert post is not None
        assert post.content == ""
    
    def test_long_content_post(self):
        """長いコンテンツでの投稿テスト"""
        long_content = "a" * 1000
        post = self.sns.create_post("user1", long_content)
        assert post is not None
        assert post.content == long_content
    
    def test_timeline_limit(self):
        """タイムライン取得制限のテスト"""
        # 多数の投稿を作成
        for i in range(60):
            self.sns.create_post("user1", f"投稿{i}")
        
        timeline = self.sns.get_global_timeline(limit=10)
        assert len(timeline) == 10
        
        timeline_all = self.sns.get_global_timeline()
        assert len(timeline_all) == 50  # デフォルト制限 