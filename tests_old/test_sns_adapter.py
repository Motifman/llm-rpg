import pytest
from src_old.systems.sns_system import SnsSystem
from src_old.systems.sns_adapter import SnsAdapter
from src_old.models.agent import Agent
from src_old.models.sns import NotificationType


class TestSnsAdapter:
    """SNSアダプターのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.sns_system = SnsSystem()
        self.sns_adapter = SnsAdapter(self.sns_system)
        
        # テスト用エージェントを作成
        self.agent1 = Agent("agent1", "エージェント1")
        self.agent2 = Agent("agent2", "エージェント2")
        self.agent3 = Agent("agent3", "エージェント3")
    
    # === エージェント登録・統合のテスト ===
    
    def test_register_agent_as_sns_user(self):
        """エージェントのSNSユーザー登録テスト"""
        sns_user = self.sns_adapter.register_agent_as_sns_user(self.agent1, "よろしくお願いします")
        
        assert sns_user is not None
        assert sns_user.user_id == self.agent1.agent_id
        assert sns_user.name == self.agent1.name
        assert sns_user.bio == "よろしくお願いします"
        assert self.sns_adapter.is_agent_registered(self.agent1)
    
    def test_register_duplicate_agent(self):
        """重複登録時の既存ユーザー返却テスト"""
        # 最初の登録
        user1 = self.sns_adapter.register_agent_as_sns_user(self.agent1, "最初の登録")
        
        # 重複登録
        user2 = self.sns_adapter.register_agent_as_sns_user(self.agent1, "重複登録")
        
        assert user1 is not None
        assert user2 is not None
        assert user1.user_id == user2.user_id
        assert user1.bio == "最初の登録"  # 最初の内容が保持される
    
    def test_get_agent_sns_profile(self):
        """エージェントのSNSプロフィール取得テスト"""
        # 未登録の場合
        profile = self.sns_adapter.get_agent_sns_profile(self.agent1)
        assert profile is None
        
        # 登録後
        self.sns_adapter.register_agent_as_sns_user(self.agent1, "テストプロフィール")
        profile = self.sns_adapter.get_agent_sns_profile(self.agent1)
        assert profile is not None
        assert profile.bio == "テストプロフィール"
    
    def test_update_agent_bio(self):
        """エージェントのプロフィール更新テスト"""
        self.sns_adapter.register_agent_as_sns_user(self.agent1, "初期プロフィール")
        
        updated_user = self.sns_adapter.update_agent_bio(self.agent1, "更新されたプロフィール")
        assert updated_user is not None
        assert updated_user.bio == "更新されたプロフィール"
        
        # ストレージからも確認
        profile = self.sns_adapter.get_agent_sns_profile(self.agent1)
        assert profile.bio == "更新されたプロフィール"
    
    # === エージェント向けSNS操作のテスト ===
    
    def test_agent_post(self):
        """エージェントの投稿テスト"""
        post = self.sns_adapter.agent_post(self.agent1, "初投稿です！", ["#初投稿"])
        
        assert post is not None
        assert post.user_id == self.agent1.agent_id
        assert post.content == "初投稿です！"
        assert "#初投稿" in post.hashtags
        
        # 自動登録されているかチェック
        assert self.sns_adapter.is_agent_registered(self.agent1)
    
    def test_agent_post_with_auto_registration(self):
        """未登録エージェントの投稿時自動登録テスト"""
        assert not self.sns_adapter.is_agent_registered(self.agent1)
        
        post = self.sns_adapter.agent_post(self.agent1, "自動登録テスト")
        
        assert post is not None
        assert self.sns_adapter.is_agent_registered(self.agent1)
        
        # 自動登録されたプロフィールを確認
        profile = self.sns_adapter.get_agent_sns_profile(self.agent1)
        assert profile.name == self.agent1.name
        assert profile.bio == ""  # デフォルトは空
    
    def test_agent_follow(self):
        """エージェントのフォローテスト"""
        result = self.sns_adapter.agent_follow(self.agent1, self.agent2)
        assert result is True
        
        # 両方のエージェントが自動登録されているかチェック
        assert self.sns_adapter.is_agent_registered(self.agent1)
        assert self.sns_adapter.is_agent_registered(self.agent2)
        
        # フォロー関係がチェック
        assert self.sns_system.is_following(self.agent1.agent_id, self.agent2.agent_id)
        
        # 通知が作成されているかチェック
        notifications = self.sns_adapter.get_agent_notifications(self.agent2)
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.FOLLOW
    
    def test_agent_unfollow(self):
        """エージェントのフォロー解除テスト"""
        self.sns_adapter.agent_follow(self.agent1, self.agent2)
        assert self.sns_system.is_following(self.agent1.agent_id, self.agent2.agent_id)
        
        result = self.sns_adapter.agent_unfollow(self.agent1, self.agent2)
        assert result is True
        assert not self.sns_system.is_following(self.agent1.agent_id, self.agent2.agent_id)
    
    def test_agent_like_post(self):
        """エージェントのいいねテスト"""
        post = self.sns_adapter.agent_post(self.agent1, "いいねテスト投稿")
        
        result = self.sns_adapter.agent_like_post(self.agent2, post.post_id)
        assert result is True
        assert self.sns_system.has_liked(self.agent2.agent_id, post.post_id)
        
        # いいね通知が作成されているかチェック
        notifications = self.sns_adapter.get_agent_notifications(self.agent1)
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.LIKE
    
    def test_agent_reply_to_post(self):
        """エージェントの返信テスト"""
        post = self.sns_adapter.agent_post(self.agent1, "返信テスト投稿")
        
        reply = self.sns_adapter.agent_reply_to_post(self.agent2, post.post_id, "返信内容です")
        assert reply is not None
        assert reply.user_id == self.agent2.agent_id
        assert reply.content == "返信内容です"
        
        # 返信通知が作成されているかチェック
        notifications = self.sns_adapter.get_agent_notifications(self.agent1)
        assert len(notifications) == 1
        assert notifications[0].type == NotificationType.REPLY
    
    # === タイムライン機能のテスト ===
    
    def test_get_agent_timeline_global(self):
        """エージェントのグローバルタイムライン取得テスト"""
        post1 = self.sns_adapter.agent_post(self.agent1, "投稿1")
        post2 = self.sns_adapter.agent_post(self.agent2, "投稿2")
        
        timeline = self.sns_adapter.get_agent_timeline(self.agent1, "global")
        assert len(timeline) == 2
        assert post1 in timeline
        assert post2 in timeline
    
    def test_get_agent_timeline_following(self):
        """エージェントのフォロー中タイムライン取得テスト"""
        # agent1がagent2をフォロー
        self.sns_adapter.agent_follow(self.agent1, self.agent2)
        
        post1 = self.sns_adapter.agent_post(self.agent1, "agent1の投稿")
        post2 = self.sns_adapter.agent_post(self.agent2, "agent2の投稿")
        post3 = self.sns_adapter.agent_post(self.agent3, "agent3の投稿")
        
        timeline = self.sns_adapter.get_agent_timeline(self.agent1, "following")
        assert len(timeline) == 1  # agent2の投稿のみ
        assert post2 in timeline
        assert post1 not in timeline
        assert post3 not in timeline
    
    def test_get_agent_timeline_user(self):
        """エージェントの個人タイムライン取得テスト"""
        post1 = self.sns_adapter.agent_post(self.agent1, "agent1の投稿1")
        post2 = self.sns_adapter.agent_post(self.agent1, "agent1の投稿2")
        post3 = self.sns_adapter.agent_post(self.agent2, "agent2の投稿")
        
        timeline = self.sns_adapter.get_agent_timeline(self.agent1, "user")
        assert len(timeline) == 2
        assert post1 in timeline
        assert post2 in timeline
        assert post3 not in timeline
    
    # === 通知機能のテスト ===
    
    def test_get_agent_notifications(self):
        """エージェントの通知取得テスト"""
        post = self.sns_adapter.agent_post(self.agent1, "通知テスト投稿")
        
        # フォロー、いいね、返信で通知を作成
        self.sns_adapter.agent_follow(self.agent2, self.agent1)
        self.sns_adapter.agent_like_post(self.agent2, post.post_id)
        self.sns_adapter.agent_reply_to_post(self.agent2, post.post_id, "返信です")
        
        notifications = self.sns_adapter.get_agent_notifications(self.agent1)
        assert len(notifications) == 3
        
        types = [n.type for n in notifications]
        assert NotificationType.FOLLOW in types
        assert NotificationType.LIKE in types
        assert NotificationType.REPLY in types
    
    def test_get_agent_unread_count(self):
        """エージェントの未読通知数取得テスト"""
        post = self.sns_adapter.agent_post(self.agent1, "未読テスト投稿")
        
        assert self.sns_adapter.get_agent_unread_count(self.agent1) == 0
        
        self.sns_adapter.agent_like_post(self.agent2, post.post_id)
        assert self.sns_adapter.get_agent_unread_count(self.agent1) == 1
        
        # 既読にマーク
        notifications = self.sns_adapter.get_agent_notifications(self.agent1, unread_only=True)
        self.sns_adapter.mark_agent_notification_read(self.agent1, notifications[0].notification_id)
        
        assert self.sns_adapter.get_agent_unread_count(self.agent1) == 0
    
    # === 統計情報のテスト ===
    
    def test_get_agent_social_stats(self):
        """エージェントのソーシャル統計取得テスト"""
        # agent1の投稿を作成
        post1 = self.sns_adapter.agent_post(self.agent1, "投稿1")
        post2 = self.sns_adapter.agent_post(self.agent1, "投稿2")
        
        # agent2、agent3がagent1をフォロー
        self.sns_adapter.agent_follow(self.agent2, self.agent1)
        self.sns_adapter.agent_follow(self.agent3, self.agent1)
        
        # agent1がagent2をフォロー
        self.sns_adapter.agent_follow(self.agent1, self.agent2)
        
        # いいねと返信を追加
        self.sns_adapter.agent_like_post(self.agent2, post1.post_id)
        self.sns_adapter.agent_like_post(self.agent3, post1.post_id)
        self.sns_adapter.agent_reply_to_post(self.agent2, post2.post_id, "返信1")
        
        stats = self.sns_adapter.get_agent_social_stats(self.agent1)
        
        assert stats["posts_count"] == 2
        assert stats["followers_count"] == 2
        assert stats["following_count"] == 1
        assert stats["total_likes_received"] == 2
        assert stats["total_replies_received"] == 1
        assert stats["unread_notifications"] == 5  # フォロー2回 + いいね2回 + 返信1回
    
    # === ハッシュタグ機能のテスト ===
    
    def test_get_hashtag_timeline(self):
        """ハッシュタグタイムライン取得テスト"""
        post1 = self.sns_adapter.agent_post(self.agent1, "楽しい一日 #日記")
        post2 = self.sns_adapter.agent_post(self.agent2, "今日も頑張る #日記 #仕事")
        post3 = self.sns_adapter.agent_post(self.agent3, "お疲れ様 #仕事")
        
        diary_timeline = self.sns_adapter.get_hashtag_timeline("日記")
        assert len(diary_timeline) == 2
        assert post1 in diary_timeline
        assert post2 in diary_timeline
        
        work_timeline = self.sns_adapter.get_hashtag_timeline("仕事")
        assert len(work_timeline) == 2
        assert post2 in work_timeline
        assert post3 in work_timeline
    
    def test_get_trending_hashtags(self):
        """トレンドハッシュタグ取得テスト"""
        self.sns_adapter.agent_post(self.agent1, "投稿1 #人気")
        self.sns_adapter.agent_post(self.agent2, "投稿2 #人気")
        self.sns_adapter.agent_post(self.agent3, "投稿3 #人気")
        self.sns_adapter.agent_post(self.agent1, "投稿4 #普通")
        
        trending = self.sns_adapter.get_trending_hashtags()
        
        assert len(trending) >= 2
        assert trending[0]["hashtag"] == "#人気"
        assert trending[0]["count"] == 3
        assert trending[1]["hashtag"] == "#普通"
        assert trending[1]["count"] == 1
    
    # === 検索機能のテスト ===
    
    def test_search_users(self):
        """ユーザー検索テスト"""
        self.sns_adapter.register_agent_as_sns_user(self.agent1, "エンジニア")
        self.sns_adapter.register_agent_as_sns_user(self.agent2, "デザイナー")
        self.sns_adapter.register_agent_as_sns_user(self.agent3, "プロダクトマネージャー")
        
        # 名前で検索
        results = self.sns_adapter.search_users("エージェント1")
        assert len(results) == 1
        assert results[0].user_id == self.agent1.agent_id
        
        # プロフィールで検索
        results = self.sns_adapter.search_users("エンジニア")
        assert len(results) == 1
        assert results[0].user_id == self.agent1.agent_id
    
    def test_search_posts(self):
        """投稿検索テスト"""
        post1 = self.sns_adapter.agent_post(self.agent1, "Python プログラミングは楽しい")
        post2 = self.sns_adapter.agent_post(self.agent2, "Java の勉強をしています")
        post3 = self.sns_adapter.agent_post(self.agent3, "今日はプログラミング三昧")
        
        results = self.sns_adapter.search_posts("プログラミング")
        assert len(results) == 2
        assert post1 in results
        assert post3 in results
        assert post2 not in results
    
    # === 詳細情報付きフィード機能のテスト ===
    
    def test_get_post_with_interactions(self):
        """投稿の詳細情報取得テスト"""
        post = self.sns_adapter.agent_post(self.agent1, "詳細情報テスト投稿")
        
        self.sns_adapter.agent_like_post(self.agent2, post.post_id)
        self.sns_adapter.agent_reply_to_post(self.agent2, post.post_id, "返信です")
        
        post_details = self.sns_adapter.get_post_with_interactions(post.post_id)
        
        assert post_details is not None
        assert post_details["post"] == post
        assert post_details["likes_count"] == 1
        assert post_details["replies_count"] == 1
        assert len(post_details["recent_replies"]) == 1
        assert post_details["author"].user_id == self.agent1.agent_id
    
    def test_get_agent_feed_with_details(self):
        """詳細情報付きフィード取得テスト"""
        post = self.sns_adapter.agent_post(self.agent1, "フィードテスト投稿")
        self.sns_adapter.agent_like_post(self.agent2, post.post_id)
        
        feed = self.sns_adapter.get_agent_feed_with_details(self.agent2, "global", limit=10)
        
        assert len(feed) == 1
        assert feed[0]["post"] == post
        assert feed[0]["likes_count"] == 1
        assert feed[0]["liked_by_agent"] is True  # agent2がいいねしている
    
    # === 関係性機能のテスト ===
    
    def test_get_mutual_follows(self):
        """相互フォロー判定テスト"""
        assert not self.sns_adapter.get_mutual_follows(self.agent1, self.agent2)
        
        # 一方向フォロー
        self.sns_adapter.agent_follow(self.agent1, self.agent2)
        assert not self.sns_adapter.get_mutual_follows(self.agent1, self.agent2)
        
        # 相互フォロー
        self.sns_adapter.agent_follow(self.agent2, self.agent1)
        assert self.sns_adapter.get_mutual_follows(self.agent1, self.agent2)
    
    def test_get_agent_relationship_status(self):
        """エージェント間関係性取得テスト"""
        # 初期状態
        status = self.sns_adapter.get_agent_relationship_status(self.agent1, self.agent2)
        assert status["is_following"] is False
        assert status["is_followed_by"] is False
        assert status["is_mutual"] is False
        
        # agent1がagent2をフォロー
        self.sns_adapter.agent_follow(self.agent1, self.agent2)
        status = self.sns_adapter.get_agent_relationship_status(self.agent1, self.agent2)
        assert status["is_following"] is True
        assert status["is_followed_by"] is False
        assert status["is_mutual"] is False
        
        # 相互フォロー
        self.sns_adapter.agent_follow(self.agent2, self.agent1)
        status = self.sns_adapter.get_agent_relationship_status(self.agent1, self.agent2)
        assert status["is_following"] is True
        assert status["is_followed_by"] is True
        assert status["is_mutual"] is True 