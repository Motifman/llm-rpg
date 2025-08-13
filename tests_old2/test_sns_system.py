import pytest
from datetime import datetime, timedelta
from game.sns.sns_manager import SnsManager
from game.sns.sns_data import SnsUser, Post, Follow, Like, Reply, Notification, Block, Mention
from game.enums import PostVisibility, NotificationType


class TestSnsManager:
    """SNSマネージャーのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.sns = SnsManager()
        
        # テスト用ユーザーを作成
        self.user1 = self.sns.create_user("user1", "アリス", "よろしくお願いします")
        self.user2 = self.sns.create_user("user2", "ボブ", "エンジニアです")
        self.user3 = self.sns.create_user("user3", "チャーリー", "")
        self.user4 = self.sns.create_user("user4", "デイビッド", "デザイナーです")
    
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
    
    def test_user_exists(self):
        """ユーザー存在チェックのテスト"""
        assert self.sns.user_exists("user1") is True
        assert self.sns.user_exists("nonexistent") is False
    
    # === 投稿機能のテスト ===
    
    def test_create_post(self):
        """投稿作成のテスト"""
        post = self.sns.create_post("user1", "こんにちは、世界！")
        
        assert post is not None
        assert post.user_id == "user1"
        assert post.content == "こんにちは、世界！"
        assert len(post.post_id) > 0
        assert isinstance(post.created_at, datetime)
        assert post.visibility == PostVisibility.PUBLIC
    
    def test_create_post_with_hashtags(self):
        """ハッシュタグ付き投稿のテスト"""
        post = self.sns.create_post("user1", "今日は良い天気 #天気 #日記", ["#初投稿"])
        
        assert post is not None
        assert "#天気" in post.hashtags
        assert "#日記" in post.hashtags
        assert "#初投稿" in post.hashtags
        assert len(set(post.hashtags)) == len(post.hashtags)  # 重複なし
    
    def test_create_post_with_extracted_hashtags(self):
        """投稿内容からハッシュタグを自動抽出するテスト"""
        post = self.sns.create_post("user1", "今日は良い天気 #天気 #日記 #初投稿")
        
        assert post is not None
        assert "#天気" in post.hashtags
        assert "#日記" in post.hashtags
        assert "#初投稿" in post.hashtags
    
    def test_create_post_nonexistent_user(self):
        """存在しないユーザーの投稿作成テスト"""
        post = self.sns.create_post("nonexistent", "テスト投稿")
        assert post is None
    
    def test_create_post_with_visibility(self):
        """可視性設定付き投稿のテスト"""
        # プライベート投稿
        private_post = self.sns.create_post("user1", "プライベート投稿", visibility=PostVisibility.PRIVATE)
        assert private_post.visibility == PostVisibility.PRIVATE
        
        # フォロワー限定投稿
        followers_post = self.sns.create_post("user1", "フォロワー限定投稿", visibility=PostVisibility.FOLLOWERS_ONLY)
        assert followers_post.visibility == PostVisibility.FOLLOWERS_ONLY
        
        # 相互フォロー限定投稿
        mutual_post = self.sns.create_post("user1", "相互フォロー限定投稿", visibility=PostVisibility.MUTUAL_FOLLOWS_ONLY)
        assert mutual_post.visibility == PostVisibility.MUTUAL_FOLLOWS_ONLY
    
    def test_create_post_with_specified_users(self):
        """指定ユーザー限定投稿のテスト"""
        post = self.sns.create_post(
            "user1", 
            "指定ユーザー限定投稿", 
            visibility=PostVisibility.SPECIFIED_USERS,
            allowed_users=["user2", "user3"]
        )
        
        assert post.visibility == PostVisibility.SPECIFIED_USERS
        assert "user2" in post.allowed_users
        assert "user3" in post.allowed_users
    
    def test_create_post_with_invalid_specified_users(self):
        """無効な指定ユーザーでの投稿作成テスト"""
        # 存在しないユーザーを指定
        post = self.sns.create_post(
            "user1", 
            "無効な指定ユーザー投稿", 
            visibility=PostVisibility.SPECIFIED_USERS,
            allowed_users=["nonexistent"]
        )
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
    
    def test_get_post(self):
        """投稿取得のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        retrieved_post = self.sns.get_post(post.post_id)
        
        assert retrieved_post is not None
        assert retrieved_post.post_id == post.post_id
        assert retrieved_post.content == "テスト投稿"
        
        # 存在しない投稿
        assert self.sns.get_post("nonexistent") is None
    
    # === タイムライン機能のテスト ===
    
    def test_global_timeline(self):
        """グローバルタイムラインのテスト"""
        # 複数の投稿を作成
        post1 = self.sns.create_post("user1", "投稿1")
        post2 = self.sns.create_post("user2", "投稿2")
        post3 = self.sns.create_post("user3", "投稿3")
        
        timeline = self.sns.get_global_timeline()
        assert len(timeline) == 3
        assert post3 in timeline  # 新しい順
        assert post2 in timeline
        assert post1 in timeline
    
    def test_global_timeline_with_viewer(self):
        """閲覧者指定のグローバルタイムラインのテスト"""
        # プライベート投稿を作成
        private_post = self.sns.create_post("user1", "プライベート投稿", visibility=PostVisibility.PRIVATE)
        public_post = self.sns.create_post("user2", "パブリック投稿")
        
        # user2から閲覧
        timeline = self.sns.get_global_timeline(viewer_id="user2")
        assert public_post in timeline
        assert private_post not in timeline  # プライベート投稿は見えない
    
    def test_following_timeline(self):
        """フォロー中タイムラインのテスト"""
        # フォロー関係を作成
        self.sns.follow_user("user1", "user2")
        self.sns.follow_user("user1", "user3")
        
        # 投稿を作成
        post1 = self.sns.create_post("user2", "user2の投稿")
        post2 = self.sns.create_post("user3", "user3の投稿")
        post3 = self.sns.create_post("user4", "user4の投稿")  # フォローしていないユーザー
        
        timeline = self.sns.get_following_timeline("user1")
        assert post1 in timeline
        assert post2 in timeline
        assert post3 not in timeline  # フォローしていないユーザーの投稿は含まれない
    
    def test_hashtag_timeline(self):
        """ハッシュタグタイムラインのテスト"""
        # ハッシュタグ付き投稿を作成
        post1 = self.sns.create_post("user1", "天気が良い #天気")
        post2 = self.sns.create_post("user2", "雨が降っている #天気")
        post3 = self.sns.create_post("user3", "普通の投稿")  # ハッシュタグなし
        
        timeline = self.sns.get_hashtag_timeline("#天気")
        assert len(timeline) == 2
        assert post1 in timeline
        assert post2 in timeline
        assert post3 not in timeline
    
    def test_hashtag_timeline_with_viewer(self):
        """閲覧者指定のハッシュタグタイムラインのテスト"""
        # プライベート投稿とパブリック投稿を作成
        private_post = self.sns.create_post("user1", "プライベート投稿 #天気", visibility=PostVisibility.PRIVATE)
        public_post = self.sns.create_post("user2", "パブリック投稿 #天気")
        
        # user3から閲覧
        timeline = self.sns.get_hashtag_timeline("#天気", viewer_id="user3")
        assert public_post in timeline
        assert private_post not in timeline  # プライベート投稿は見えない
    
    # === フォロー機能のテスト ===
    
    def test_follow_user(self):
        """ユーザーフォローのテスト"""
        result = self.sns.follow_user("user1", "user2")
        assert result is True
        
        # フォロー関係を確認
        assert self.sns.is_following("user1", "user2") is True
        assert self.sns.is_following("user2", "user1") is False  # 逆方向はフォローしていない
    
    def test_follow_self(self):
        """自分自身をフォローするテスト（失敗する）"""
        result = self.sns.follow_user("user1", "user1")
        assert result is False
    
    def test_follow_nonexistent_user(self):
        """存在しないユーザーをフォローするテスト（失敗する）"""
        result = self.sns.follow_user("user1", "nonexistent")
        assert result is False
    
    def test_duplicate_follow(self):
        """重複フォローのテスト（失敗する）"""
        self.sns.follow_user("user1", "user2")
        result = self.sns.follow_user("user1", "user2")  # 再度フォロー
        assert result is False
    
    def test_unfollow_user(self):
        """フォロー解除のテスト"""
        self.sns.follow_user("user1", "user2")
        assert self.sns.is_following("user1", "user2") is True
        
        result = self.sns.unfollow_user("user1", "user2")
        assert result is True
        assert self.sns.is_following("user1", "user2") is False
    
    def test_unfollow_not_following(self):
        """フォローしていないユーザーのフォロー解除テスト"""
        result = self.sns.unfollow_user("user1", "user2")
        assert result is False
    
    def test_follow_counts(self):
        """フォロー数のテスト"""
        # フォロー関係を作成
        self.sns.follow_user("user1", "user2")
        self.sns.follow_user("user1", "user3")
        self.sns.follow_user("user2", "user1")
        
        assert self.sns.get_following_count("user1") == 2
        assert self.sns.get_followers_count("user1") == 1
        assert self.sns.get_following_count("user2") == 1
        assert self.sns.get_followers_count("user2") == 1
    
    def test_follow_lists(self):
        """フォローリストのテスト"""
        # フォロー関係を作成
        self.sns.follow_user("user1", "user2")
        self.sns.follow_user("user1", "user3")
        self.sns.follow_user("user2", "user1")
        
        following_list = self.sns.get_following_list("user1")
        assert "user2" in following_list
        assert "user3" in following_list
        assert len(following_list) == 2
        
        followers_list = self.sns.get_followers_list("user1")
        assert "user2" in followers_list
        assert len(followers_list) == 1
    
    # === ブロック機能のテスト ===
    
    def test_block_user(self):
        """ユーザーブロックのテスト"""
        result = self.sns.block_user("user1", "user2")
        assert result is True
        
        # ブロック関係を確認
        assert self.sns.is_blocked("user1", "user2") is True
        assert self.sns.is_blocked("user2", "user1") is False  # 逆方向はブロックしていない
    
    def test_block_self(self):
        """自分自身をブロックするテスト（失敗する）"""
        result = self.sns.block_user("user1", "user1")
        assert result is False
    
    def test_block_nonexistent_user(self):
        """存在しないユーザーをブロックするテスト（失敗する）"""
        result = self.sns.block_user("user1", "nonexistent")
        assert result is False
    
    def test_duplicate_block(self):
        """重複ブロックのテスト（失敗する）"""
        self.sns.block_user("user1", "user2")
        result = self.sns.block_user("user1", "user2")  # 再度ブロック
        assert result is False
    
    def test_unblock_user(self):
        """ブロック解除のテスト"""
        self.sns.block_user("user1", "user2")
        assert self.sns.is_blocked("user1", "user2") is True
        
        result = self.sns.unblock_user("user1", "user2")
        assert result is True
        assert self.sns.is_blocked("user1", "user2") is False
    
    def test_unblock_not_blocking(self):
        """ブロックしていないユーザーのブロック解除テスト"""
        result = self.sns.unblock_user("user1", "user2")
        assert result is False
    
    def test_block_auto_unfollow(self):
        """ブロック時の自動フォロー解除テスト"""
        # フォロー関係を作成
        self.sns.follow_user("user1", "user2")
        self.sns.follow_user("user2", "user1")
        
        # ブロック
        self.sns.block_user("user1", "user2")
        
        # フォロー関係が解除されているか確認
        assert self.sns.is_following("user1", "user2") is False
        assert self.sns.is_following("user2", "user1") is False
    
    def test_block_lists(self):
        """ブロックリストのテスト"""
        # ブロック関係を作成
        self.sns.block_user("user1", "user2")
        self.sns.block_user("user1", "user3")
        self.sns.block_user("user2", "user1")
        
        blocked_list = self.sns.get_blocked_list("user1")
        assert "user2" in blocked_list
        assert "user3" in blocked_list
        assert len(blocked_list) == 2
        
        blocked_by_list = self.sns.get_blocked_by_list("user1")
        assert "user2" in blocked_by_list
        assert len(blocked_by_list) == 1
    
    def test_block_counts(self):
        """ブロック数のテスト"""
        self.sns.block_user("user1", "user2")
        self.sns.block_user("user1", "user3")
        self.sns.block_user("user2", "user1")
        
        assert self.sns.get_blocked_count("user1") == 2
        assert self.sns.get_blocked_count("user2") == 1
        assert self.sns.get_blocked_count("user3") == 0
    
    # === いいね機能のテスト ===
    
    def test_like_post(self):
        """投稿へのいいねのテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        result = self.sns.like_post("user2", post.post_id)
        
        assert result is True
        assert self.sns.has_liked("user2", post.post_id) is True
        assert self.sns.get_post_likes_count(post.post_id) == 1
    
    def test_like_own_post(self):
        """自分の投稿へのいいねのテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        result = self.sns.like_post("user1", post.post_id)
        
        assert result is True
        assert self.sns.has_liked("user1", post.post_id) is True
    
    def test_duplicate_like(self):
        """重複いいねのテスト（失敗する）"""
        post = self.sns.create_post("user1", "テスト投稿")
        self.sns.like_post("user2", post.post_id)
        result = self.sns.like_post("user2", post.post_id)  # 再度いいね
        assert result is False
    
    def test_like_private_post(self):
        """プライベート投稿へのいいねのテスト（失敗する）"""
        post = self.sns.create_post("user1", "プライベート投稿", visibility=PostVisibility.PRIVATE)
        result = self.sns.like_post("user2", post.post_id)
        assert result is False
    
    def test_unlike_post(self):
        """いいね解除のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        self.sns.like_post("user2", post.post_id)
        assert self.sns.has_liked("user2", post.post_id) is True
        
        result = self.sns.unlike_post("user2", post.post_id)
        assert result is True
        assert self.sns.has_liked("user2", post.post_id) is False
    
    def test_unlike_not_liked(self):
        """いいねしていない投稿のいいね解除テスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        result = self.sns.unlike_post("user2", post.post_id)
        assert result is False
    
    # === 返信機能のテスト ===
    
    def test_reply_to_post(self):
        """投稿への返信のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        reply = self.sns.reply_to_post("user2", post.post_id, "返信です")
        
        assert reply is not None
        assert reply.user_id == "user2"
        assert reply.post_id == post.post_id
        assert reply.content == "返信です"
    
    def test_reply_to_own_post(self):
        """自分の投稿への返信のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        reply = self.sns.reply_to_post("user1", post.post_id, "自分の投稿への返信")
        
        assert reply is not None
        assert reply.user_id == "user1"
    
    def test_reply_to_private_post(self):
        """プライベート投稿への返信のテスト（失敗する）"""
        post = self.sns.create_post("user1", "プライベート投稿", visibility=PostVisibility.PRIVATE)
        reply = self.sns.reply_to_post("user2", post.post_id, "返信です")
        assert reply is None
    
    def test_get_post_replies(self):
        """投稿の返信取得のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        reply1 = self.sns.reply_to_post("user2", post.post_id, "返信1")
        reply2 = self.sns.reply_to_post("user3", post.post_id, "返信2")
        
        replies = self.sns.get_post_replies(post.post_id)
        assert len(replies) == 2
        assert reply1 in replies
        assert reply2 in replies
    
    def test_get_post_replies_count(self):
        """投稿の返信数のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        self.sns.reply_to_post("user2", post.post_id, "返信1")
        self.sns.reply_to_post("user3", post.post_id, "返信2")
        
        assert self.sns.get_post_replies_count(post.post_id) == 2
    
    # === 通知機能のテスト ===
    
    def test_follow_notification(self):
        """フォロー通知のテスト"""
        self.sns.follow_user("user1", "user2")
        
        notifications = self.sns.get_user_notifications("user2")
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.FOLLOW
        assert notifications[0].from_user_id == "user1"
    
    def test_like_notification(self):
        """いいね通知のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        self.sns.like_post("user2", post.post_id)
        
        notifications = self.sns.get_user_notifications("user1")
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.LIKE
        assert notifications[0].from_user_id == "user2"
    
    def test_reply_notification(self):
        """返信通知のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        self.sns.reply_to_post("user2", post.post_id, "返信です")
        
        notifications = self.sns.get_user_notifications("user1")
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.REPLY
        assert notifications[0].from_user_id == "user2"
    
    def test_mention_notification(self):
        """メンション通知のテスト"""
        post = self.sns.create_post("user1", "こんにちは @user2")
        
        notifications = self.sns.get_user_notifications("user2")
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.MENTION
        assert notifications[0].from_user_id == "user1"
    
    def test_get_user_notifications(self):
        """ユーザー通知取得のテスト"""
        # 複数の通知を作成
        self.sns.follow_user("user1", "user2")
        post = self.sns.create_post("user2", "テスト投稿")
        self.sns.like_post("user1", post.post_id)
        
        notifications = self.sns.get_user_notifications("user2")
        assert len(notifications) == 2
    
    def test_get_unread_notifications(self):
        """未読通知取得のテスト"""
        self.sns.follow_user("user1", "user2")
        
        unread_notifications = self.sns.get_user_notifications("user2", unread_only=True)
        assert len(unread_notifications) == 1
        
        # 通知を既読にする
        notification_id = unread_notifications[0].notification_id
        self.sns.mark_notification_as_read(notification_id)
        
        unread_notifications = self.sns.get_user_notifications("user2", unread_only=True)
        assert len(unread_notifications) == 0
    
    def test_mark_notification_as_read(self):
        """通知既読マークのテスト"""
        self.sns.follow_user("user1", "user2")
        
        notifications = self.sns.get_user_notifications("user2")
        notification_id = notifications[0].notification_id
        
        result = self.sns.mark_notification_as_read(notification_id)
        assert result is True
        
        # 既読になっているか確認
        updated_notifications = self.sns.get_user_notifications("user2")
        assert updated_notifications[0].is_read is True
    
    def test_get_unread_notifications_count(self):
        """未読通知数のテスト"""
        self.sns.follow_user("user1", "user2")
        post = self.sns.create_post("user2", "テスト投稿")
        self.sns.like_post("user1", post.post_id)
        
        unread_count = self.sns.get_unread_notifications_count("user2")
        assert unread_count == 2
    
    # === メンション機能のテスト ===
    
    def test_mention_in_post(self):
        """投稿内メンションのテスト"""
        post = self.sns.create_post("user1", "こんにちは @user2 と @user3")
        
        mentions = self.sns.get_mentions_for_user("user2")
        assert len(mentions) == 1
        assert mentions[0].user_id == "user1"
        assert mentions[0].mentioned_user_id == "user2"
        
        mentions = self.sns.get_mentions_for_user("user3")
        assert len(mentions) == 1
        assert mentions[0].user_id == "user1"
        assert mentions[0].mentioned_user_id == "user3"
    
    def test_mention_in_reply(self):
        """返信内メンションのテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        reply = self.sns.reply_to_post("user2", post.post_id, "返信です @user3")
        
        mentions = self.sns.get_mentions_for_user("user3")
        assert len(mentions) == 1
        assert mentions[0].reply_id == reply.reply_id
    
    def test_mention_nonexistent_user(self):
        """存在しないユーザーへのメンションのテスト"""
        post = self.sns.create_post("user1", "こんにちは @nonexistent")
        
        # 存在しないユーザーへのメンションは無視される
        mentions = self.sns.get_mentions_for_user("nonexistent")
        assert len(mentions) == 0
    
    def test_mention_self(self):
        """自分自身へのメンションのテスト（通知されない）"""
        post = self.sns.create_post("user1", "こんにちは @user1")
        
        # 自分自身へのメンションは通知されない
        notifications = self.sns.get_user_notifications("user1")
        assert len(notifications) == 0
    
    def test_get_mentions_by_user(self):
        """ユーザーが行ったメンションの取得テスト"""
        post = self.sns.create_post("user1", "こんにちは @user2")
        
        mentions = self.sns.get_mentions_by_user("user1")
        assert len(mentions) == 1
        assert mentions[0].mentioned_user_id == "user2"
    
    def test_get_mentions_for_post(self):
        """投稿のメンション取得テスト"""
        post = self.sns.create_post("user1", "こんにちは @user2 と @user3")
        
        mentions = self.sns.get_mentions_for_post(post.post_id)
        assert len(mentions) == 2
    
    # === 可視性制限のテスト ===
    
    def test_post_visibility_public(self):
        """パブリック投稿の可視性テスト"""
        post = self.sns.create_post("user1", "パブリック投稿", visibility=PostVisibility.PUBLIC)
        
        # 誰でも見える
        assert self.sns._is_post_visible(post, "user2") is True
        assert self.sns._is_post_visible(post, "user3") is True
    
    def test_post_visibility_private(self):
        """プライベート投稿の可視性テスト"""
        post = self.sns.create_post("user1", "プライベート投稿", visibility=PostVisibility.PRIVATE)
        
        # 本人のみ見える
        assert self.sns._is_post_visible(post, "user1") is True
        assert self.sns._is_post_visible(post, "user2") is False
    
    def test_post_visibility_followers_only(self):
        """フォロワー限定投稿の可視性テスト"""
        post = self.sns.create_post("user1", "フォロワー限定投稿", visibility=PostVisibility.FOLLOWERS_ONLY)
        
        # フォロー関係を作成
        self.sns.follow_user("user2", "user1")
        
        # フォロワーのみ見える
        assert self.sns._is_post_visible(post, "user1") is True  # 本人
        assert self.sns._is_post_visible(post, "user2") is True   # フォロワー
        assert self.sns._is_post_visible(post, "user3") is False  # フォローしていない
    
    def test_post_visibility_mutual_follows_only(self):
        """相互フォロー限定投稿の可視性テスト"""
        post = self.sns.create_post("user1", "相互フォロー限定投稿", visibility=PostVisibility.MUTUAL_FOLLOWS_ONLY)
        
        # 片方向フォロー
        self.sns.follow_user("user2", "user1")
        
        # 相互フォローでない場合は見えない
        assert self.sns._is_post_visible(post, "user1") is True  # 本人
        assert self.sns._is_post_visible(post, "user2") is False  # 片方向フォロー
        
        # 相互フォローにする
        self.sns.follow_user("user1", "user2")
        
        # 相互フォローなら見える
        assert self.sns._is_post_visible(post, "user2") is True
    
    def test_post_visibility_specified_users(self):
        """指定ユーザー限定投稿の可視性テスト"""
        post = self.sns.create_post(
            "user1", 
            "指定ユーザー限定投稿", 
            visibility=PostVisibility.SPECIFIED_USERS,
            allowed_users=["user2", "user3"]
        )
        
        # 指定ユーザーのみ見える
        assert self.sns._is_post_visible(post, "user1") is True  # 本人
        assert self.sns._is_post_visible(post, "user2") is True   # 指定ユーザー
        assert self.sns._is_post_visible(post, "user3") is True   # 指定ユーザー
        assert self.sns._is_post_visible(post, "user4") is False  # 指定されていない
    
    def test_block_visibility_restriction(self):
        """ブロックによる可視性制限のテスト"""
        post = self.sns.create_post("user1", "テスト投稿")
        
        # user1がuser2をブロック
        self.sns.block_user("user1", "user2")
        
        # ブロックされたユーザーは投稿が見えない
        assert self.sns._is_post_visible(post, "user2") is False
        
        # 逆方向のブロック
        self.sns.block_user("user2", "user1")
        
        # ブロックしたユーザーも投稿が見えない
        assert self.sns._is_post_visible(post, "user2") is False
    
    # === 統計機能のテスト ===
    
    def test_system_stats(self):
        """システム統計のテスト"""
        # 各種データを作成
        self.sns.follow_user("user1", "user2")
        post = self.sns.create_post("user1", "テスト投稿")
        self.sns.like_post("user2", post.post_id)
        self.sns.reply_to_post("user2", post.post_id, "返信")
        self.sns.block_user("user1", "user3")
        
        stats = self.sns.get_system_stats()
        
        assert stats["total_users"] == 4
        assert stats["total_posts"] == 1
        assert stats["total_follows"] == 1
        assert stats["total_likes"] == 1
        assert stats["total_replies"] == 1
        assert stats["total_blocks"] == 1
        assert "public" in stats["posts_by_visibility"]
    
    # === エッジケースのテスト ===
    
    def test_empty_content_post(self):
        """空の内容での投稿テスト"""
        post = self.sns.create_post("user1", "")
        assert post is not None
        assert post.content == ""
    
    def test_long_content_post(self):
        """長い内容での投稿テスト"""
        long_content = "a" * 1000
        post = self.sns.create_post("user1", long_content)
        assert post is not None
        assert post.content == long_content
    
    def test_timeline_limit(self):
        """タイムラインの制限テスト"""
        # 複数の投稿を作成
        for i in range(10):
            self.sns.create_post("user1", f"投稿{i}")
        
        timeline = self.sns.get_global_timeline(limit=5)
        assert len(timeline) == 5
    
    def test_mention_with_special_characters(self):
        """特殊文字を含むメンションのテスト"""
        post = self.sns.create_post("user1", "こんにちは @user2! と @user3.")
        
        mentions = self.sns.get_mentions_for_user("user2")
        assert len(mentions) == 1
        
        mentions = self.sns.get_mentions_for_user("user3")
        assert len(mentions) == 1
    
    def test_hashtag_with_special_characters(self):
        """特殊文字を含むハッシュタグのテスト"""
        post = self.sns.create_post("user1", "テスト投稿 #test-hash_tag #test@hash")
        
        assert "#test-hash_tag" in post.hashtags
        assert "#test@hash" in post.hashtags
    
    def test_multiple_mentions_same_user(self):
        """同一ユーザーへの複数メンションのテスト"""
        post = self.sns.create_post("user1", "こんにちは @user2 と @user2")
        
        mentions = self.sns.get_mentions_for_user("user2")
        assert len(mentions) == 1  # 重複は除去される
    
    def test_mention_in_private_post(self):
        """プライベート投稿内のメンションのテスト"""
        post = self.sns.create_post("user1", "プライベート投稿 @user2", visibility=PostVisibility.PRIVATE)
        
        # プライベート投稿内のメンションは通知されない
        notifications = self.sns.get_user_notifications("user2")
        assert len(notifications) == 0 