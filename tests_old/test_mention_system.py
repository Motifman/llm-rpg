import pytest
from datetime import datetime
from src.systems.sns_system import SnsSystem
from src.models.sns import NotificationType, PostVisibility


class TestMentionSystem:
    """メンション機能のテスト"""
    
    def setup_method(self):
        """各テストの前に実行される初期化"""
        self.sns = SnsSystem()
        
        # テスト用ユーザーを作成
        self.alice = self.sns.create_user("alice", "Alice")
        self.bob = self.sns.create_user("bob", "Bob")
        self.charlie = self.sns.create_user("charlie", "Charlie")
        self.dave = self.sns.create_user("dave", "Dave")
    
    def test_extract_mentions_from_post_content(self):
        """投稿内容からメンションを抽出するテスト"""
        # 投稿作成
        post = self.sns.create_post("alice", "こんにちは @Bob さん！今度 @Charlie と会いませんか？")
        
        # メンション抽出の確認
        mentions = post.extract_mentions_from_content()
        assert "Bob" in mentions
        assert "Charlie" in mentions
        assert len(mentions) == 2
    
    def test_extract_mentions_from_reply_content(self):
        """返信内容からメンションを抽出するテスト"""
        # 投稿とリプライ作成
        post = self.sns.create_post("alice", "テスト投稿")
        reply = self.sns.reply_to_post("bob", post.post_id, "それは良いアイデアですね @Alice！@Charlie も参加しますか？")
        
        # メンション抽出の確認
        mentions = reply.extract_mentions_from_content()
        assert "Alice" in mentions
        assert "Charlie" in mentions
        assert len(mentions) == 2
    
    def test_mention_processing_in_post(self):
        """投稿内のメンション処理のテスト"""
        # メンション付き投稿を作成
        post = self.sns.create_post("alice", "こんにちは @Bob さん！")
        
        # メンション記録の確認
        mentions = self.sns.get_mentions_for_post(post.post_id)
        assert len(mentions) == 1
        assert mentions[0].user_id == "alice"
        assert mentions[0].mentioned_user_id == "bob"
        assert mentions[0].post_id == post.post_id
        assert mentions[0].reply_id is None
        
        # メンション通知の確認
        bob_notifications = self.sns.get_user_notifications("bob")
        mention_notifications = [n for n in bob_notifications if n.type == NotificationType.MENTION]
        assert len(mention_notifications) == 1
        assert mention_notifications[0].from_user_id == "alice"
        assert "投稿でメンション" in mention_notifications[0].content
    
    def test_mention_processing_in_reply(self):
        """返信内のメンション処理のテスト"""
        # 投稿を作成
        post = self.sns.create_post("alice", "テスト投稿")
        
        # メンション付き返信を作成
        reply = self.sns.reply_to_post("bob", post.post_id, "同感です @Charlie！")
        
        # メンション記録の確認
        mentions = self.sns.get_mentions_for_post(post.post_id)
        assert len(mentions) == 1
        assert mentions[0].user_id == "bob"
        assert mentions[0].mentioned_user_id == "charlie"
        assert mentions[0].post_id == post.post_id
        assert mentions[0].reply_id == reply.reply_id
        
        # メンション通知の確認
        charlie_notifications = self.sns.get_user_notifications("charlie")
        mention_notifications = [n for n in charlie_notifications if n.type == NotificationType.MENTION]
        assert len(mention_notifications) == 1
        assert mention_notifications[0].from_user_id == "bob"
        assert "返信でメンション" in mention_notifications[0].content
    
    def test_multiple_mentions_in_single_post(self):
        """1つの投稿に複数のメンションがある場合のテスト"""
        # 複数メンション付き投稿を作成
        post = self.sns.create_post("alice", "みなさん (@Bob @Charlie @Dave) お疲れさまでした！")
        
        # メンション記録の確認
        mentions = self.sns.get_mentions_for_post(post.post_id)
        assert len(mentions) == 3
        
        mentioned_users = [m.mentioned_user_id for m in mentions]
        assert "bob" in mentioned_users
        assert "charlie" in mentioned_users
        assert "dave" in mentioned_users
        
        # 各ユーザーに通知が送られているか確認
        for user_id in ["bob", "charlie", "dave"]:
            notifications = self.sns.get_user_notifications(user_id)
            mention_notifications = [n for n in notifications if n.type == NotificationType.MENTION]
            assert len(mention_notifications) == 1
    
    def test_self_mention_ignored(self):
        """自分自身へのメンションは無視されるテスト"""
        # 自分自身をメンションした投稿を作成
        post = self.sns.create_post("alice", "今日は忙しい一日でした @Alice さん、お疲れさま！")
        
        # メンション記録の確認（自分へのメンションは記録されない）
        mentions = self.sns.get_mentions_for_post(post.post_id)
        assert len(mentions) == 0
        
        # 自分に通知は送られない
        alice_notifications = self.sns.get_user_notifications("alice")
        mention_notifications = [n for n in alice_notifications if n.type == NotificationType.MENTION]
        assert len(mention_notifications) == 0
    
    def test_nonexistent_user_mention(self):
        """存在しないユーザーのメンションのテスト"""
        # 存在しないユーザーをメンション
        post = self.sns.create_post("alice", "こんにちは @NonexistentUser さん！")
        
        # メンション記録の確認（存在しないユーザーは記録されない）
        mentions = self.sns.get_mentions_for_post(post.post_id)
        assert len(mentions) == 0
    
    def test_blocked_user_mention(self):
        """ブロックしたユーザーをメンションした場合のテスト"""
        # ブロック関係を設定
        self.sns.block_user("alice", "bob")
        
        # ブロックしたユーザーをメンション
        post = self.sns.create_post("alice", "こんにちは @Bob さん！")
        
        # メンション記録の確認（ブロック関係がある場合は記録されない）
        mentions = self.sns.get_mentions_for_post(post.post_id)
        assert len(mentions) == 0
        
        # ブロックしたユーザーに通知は送られない
        bob_notifications = self.sns.get_user_notifications("bob")
        mention_notifications = [n for n in bob_notifications if n.type == NotificationType.MENTION]
        assert len(mention_notifications) == 0
    
    def test_private_post_mention(self):
        """プライベート投稿でのメンションのテスト"""
        # プライベート投稿でメンション（メンション処理は行われない）
        post = self.sns.create_post("alice", "プライベートメモ @Bob", visibility=PostVisibility.PRIVATE)
        
        # メンション記録の確認（プライベート投稿では処理されない）
        mentions = self.sns.get_mentions_for_post(post.post_id)
        assert len(mentions) == 0
        
        # 通知も送られない
        bob_notifications = self.sns.get_user_notifications("bob")
        mention_notifications = [n for n in bob_notifications if n.type == NotificationType.MENTION]
        assert len(mention_notifications) == 0
    
    def test_get_mentions_for_user(self):
        """ユーザーがメンションされた記録を取得するテスト"""
        # 複数の投稿でbobをメンション
        post1 = self.sns.create_post("alice", "こんにちは @Bob さん！")
        post2 = self.sns.create_post("charlie", "@Bob お疲れさまです！")
        
        # bobがメンションされた記録を取得
        bob_mentions = self.sns.get_mentions_for_user("bob")
        assert len(bob_mentions) == 2
        
        # メンション元ユーザーの確認
        mention_users = [m.user_id for m in bob_mentions]
        assert "alice" in mention_users
        assert "charlie" in mention_users
    
    def test_get_mentions_by_user(self):
        """ユーザーが行ったメンションを取得するテスト"""
        # aliceが複数のユーザーをメンション
        post1 = self.sns.create_post("alice", "こんにちは @Bob さん！")
        post2 = self.sns.create_post("alice", "@Charlie お疲れさまです！")
        
        # aliceが行ったメンションを取得
        alice_mentions = self.sns.get_mentions_by_user("alice")
        assert len(alice_mentions) == 2
        
        # メンション先ユーザーの確認
        mentioned_users = [m.mentioned_user_id for m in alice_mentions]
        assert "bob" in mentioned_users
        assert "charlie" in mentioned_users
    
    def test_find_user_by_name(self):
        """ユーザー名からユーザーIDを検索するテスト"""
        # ユーザー名から検索
        alice_id = self.sns._find_user_by_name("Alice")
        assert alice_id == "alice"
        
        bob_id = self.sns._find_user_by_name("Bob")
        assert bob_id == "bob"
        
        # 存在しないユーザー名
        nonexistent_id = self.sns._find_user_by_name("NonExistent")
        assert nonexistent_id is None
    
    def test_mention_notification_content(self):
        """メンション通知の内容のテスト"""
        # 投稿でのメンション
        post = self.sns.create_post("alice", "こんにちは @Bob さん！")
        bob_notifications = self.sns.get_user_notifications("bob")
        post_mention_notification = [n for n in bob_notifications if n.type == NotificationType.MENTION][0]
        assert "alice" in post_mention_notification.content
        assert "投稿でメンション" in post_mention_notification.content
        
        # 返信でのメンション
        reply = self.sns.reply_to_post("charlie", post.post_id, "同感です @Bob！")
        bob_notifications = self.sns.get_user_notifications("bob")
        reply_mention_notifications = [n for n in bob_notifications 
                                     if n.type == NotificationType.MENTION and n.from_user_id == "charlie"]
        assert len(reply_mention_notifications) == 1
        assert "charlie" in reply_mention_notifications[0].content
        assert "返信でメンション" in reply_mention_notifications[0].content
    
    def test_system_stats_includes_mentions(self):
        """システム統計にメンション数が含まれるテスト"""
        # メンション付き投稿を作成
        self.sns.create_post("alice", "こんにちは @Bob さん！")
        self.sns.create_post("charlie", "@Bob @Dave お疲れさまです！")
        
        # 統計情報の確認
        stats = self.sns.get_system_stats()
        assert "total_mentions" in stats
        assert stats["total_mentions"] == 3  # bob×1 + bob×1 + dave×1
    
    def test_complex_mention_scenario(self):
        """複雑なメンションシナリオのテスト"""
        # フォロー関係を設定
        self.sns.follow_user("alice", "bob")
        self.sns.follow_user("bob", "alice")
        
        # 投稿、返信、メンションの組み合わせ
        post = self.sns.create_post("alice", "プロジェクトについて @Bob と話しましょう！")
        reply1 = self.sns.reply_to_post("bob", post.post_id, "いいですね！@Charlie も巻き込みましょう")
        reply2 = self.sns.reply_to_post("charlie", post.post_id, "参加します！@Alice @Bob よろしくお願いします")
        
        # メンション記録の確認
        post_mentions = self.sns.get_mentions_for_post(post.post_id)
        assert len(post_mentions) == 4  # bob×1, charlie×1, alice×1, bob×1
        
        # 通知の確認
        bob_notifications = self.sns.get_user_notifications("bob")
        charlie_notifications = self.sns.get_user_notifications("charlie")
        alice_notifications = self.sns.get_user_notifications("alice")
        
        # Bobの通知：メンション×2（投稿から1回、返信から1回）
        bob_mention_notifications = [n for n in bob_notifications if n.type == NotificationType.MENTION]
        assert len(bob_mention_notifications) == 2
        
        # Charlieの通知：メンション×1（返信から1回）
        charlie_mention_notifications = [n for n in charlie_notifications if n.type == NotificationType.MENTION]
        assert len(charlie_mention_notifications) == 1
        
        # Aliceの通知：メンション×1（返信から1回）
        alice_mention_notifications = [n for n in alice_notifications if n.type == NotificationType.MENTION]
        assert len(alice_mention_notifications) == 1 