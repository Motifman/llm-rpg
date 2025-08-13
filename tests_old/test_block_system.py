import pytest
from src_old.systems.sns_system import SnsSystem
from src_old.systems.sns_adapter import SnsAdapter
from src_old.models.agent import Agent
from src_old.models.sns import NotificationType


class TestBlockSystem:
    """ブロック機能のテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.sns_system = SnsSystem()
        self.sns_adapter = SnsAdapter(self.sns_system)
        
        # テスト用エージェントを作成
        self.alice = Agent("alice", "アリス")
        self.bob = Agent("bob", "ボブ")
        self.charlie = Agent("charlie", "チャーリー")
        
        # エージェントをSNSに登録
        self.sns_adapter.register_agent_as_sns_user(self.alice)
        self.sns_adapter.register_agent_as_sns_user(self.bob)
        self.sns_adapter.register_agent_as_sns_user(self.charlie)
    
    # === 基本的なブロック機能のテスト ===
    
    def test_block_user(self):
        """ユーザーブロック機能のテスト"""
        result = self.sns_system.block_user("alice", "bob")
        assert result is True
        assert self.sns_system.is_blocked("alice", "bob")
        assert not self.sns_system.is_blocked("bob", "alice")  # 一方向のブロック
    
    def test_block_self(self):
        """自分自身をブロックするテスト"""
        result = self.sns_system.block_user("alice", "alice")
        assert result is False
    
    def test_block_nonexistent_user(self):
        """存在しないユーザーをブロックするテスト"""
        result = self.sns_system.block_user("alice", "nonexistent")
        assert result is False
    
    def test_duplicate_block(self):
        """重複ブロックのテスト"""
        self.sns_system.block_user("alice", "bob")
        result = self.sns_system.block_user("alice", "bob")
        assert result is False
    
    def test_unblock_user(self):
        """ブロック解除のテスト"""
        self.sns_system.block_user("alice", "bob")
        assert self.sns_system.is_blocked("alice", "bob")
        
        result = self.sns_system.unblock_user("alice", "bob")
        assert result is True
        assert not self.sns_system.is_blocked("alice", "bob")
    
    def test_unblock_nonexistent_block(self):
        """存在しないブロック関係の解除テスト"""
        result = self.sns_system.unblock_user("alice", "bob")
        assert result is False
    
    def test_block_lists(self):
        """ブロックリスト取得のテスト"""
        self.sns_system.block_user("alice", "bob")
        self.sns_system.block_user("alice", "charlie")
        self.sns_system.block_user("bob", "alice")
        
        # アリスのブロックリスト
        blocked_by_alice = self.sns_system.get_blocked_list("alice")
        assert "bob" in blocked_by_alice
        assert "charlie" in blocked_by_alice
        assert len(blocked_by_alice) == 2
        
        # アリスをブロックしているユーザーリスト
        blocking_alice = self.sns_system.get_blocked_by_list("alice")
        assert "bob" in blocking_alice
        assert len(blocking_alice) == 1
        
        # ブロック数
        assert self.sns_system.get_blocked_count("alice") == 2
    
    # === ブロック時の自動フォロー解除テスト ===
    
    def test_block_removes_follow_relationships(self):
        """ブロック時の自動フォロー解除テスト"""
        # 相互フォローを設定
        self.sns_system.follow_user("alice", "bob")
        self.sns_system.follow_user("bob", "alice")
        
        assert self.sns_system.is_following("alice", "bob")
        assert self.sns_system.is_following("bob", "alice")
        
        # アリスがボブをブロック
        self.sns_system.block_user("alice", "bob")
        
        # 両方向のフォロー関係が解除される
        assert not self.sns_system.is_following("alice", "bob")
        assert not self.sns_system.is_following("bob", "alice")
    
    # === ブロック制限のテスト ===
    
    def test_blocked_user_cannot_follow(self):
        """ブロックされたユーザーはフォローできないテスト"""
        self.sns_system.block_user("alice", "bob")
        
        # ボブからアリスへのフォローは拒否される
        result = self.sns_system.follow_user("bob", "alice")
        assert result is False
        
        # アリスからボブへのフォローも拒否される
        result = self.sns_system.follow_user("alice", "bob")
        assert result is False
    
    def test_blocked_user_cannot_like_posts(self):
        """ブロックされたユーザーは投稿にいいねできないテスト"""
        # アリスが投稿
        post = self.sns_system.create_post("alice", "テスト投稿")
        
        # ボブをブロック
        self.sns_system.block_user("alice", "bob")
        
        # ボブはアリスの投稿にいいねできない
        result = self.sns_system.like_post("bob", post.post_id)
        assert result is False
        
        # アリスもボブの投稿にいいねできない（逆方向）
        bob_post = self.sns_system.create_post("bob", "ボブの投稿")
        result = self.sns_system.like_post("alice", bob_post.post_id)
        assert result is False
    
    def test_blocked_user_cannot_reply_to_posts(self):
        """ブロックされたユーザーは投稿に返信できないテスト"""
        # アリスが投稿
        post = self.sns_system.create_post("alice", "テスト投稿")
        
        # ボブをブロック
        self.sns_system.block_user("alice", "bob")
        
        # ボブはアリスの投稿に返信できない
        reply = self.sns_system.reply_to_post("bob", post.post_id, "返信内容")
        assert reply is None
        
        # アリスもボブの投稿に返信できない（逆方向）
        bob_post = self.sns_system.create_post("bob", "ボブの投稿")
        reply = self.sns_system.reply_to_post("alice", bob_post.post_id, "返信内容")
        assert reply is None
    
    # === タイムラインでのブロック制限テスト ===
    
    def test_blocked_posts_not_in_global_timeline(self):
        """ブロックされたユーザーの投稿はグローバルタイムラインに表示されないテスト"""
        # 投稿を作成
        alice_post = self.sns_system.create_post("alice", "アリスの投稿")
        bob_post = self.sns_system.create_post("bob", "ボブの投稿")
        charlie_post = self.sns_system.create_post("charlie", "チャーリーの投稿")
        
        # アリスがボブをブロック
        self.sns_system.block_user("alice", "bob")
        
        # アリスのグローバルタイムライン（ボブの投稿は表示されない）
        alice_timeline = self.sns_system.get_global_timeline(viewer_id="alice")
        timeline_user_ids = [post.user_id for post in alice_timeline]
        
        assert "alice" in timeline_user_ids
        assert "charlie" in timeline_user_ids
        assert "bob" not in timeline_user_ids
        
        # ボブのグローバルタイムライン（アリスの投稿は表示されない）
        bob_timeline = self.sns_system.get_global_timeline(viewer_id="bob")
        timeline_user_ids = [post.user_id for post in bob_timeline]
        
        assert "bob" in timeline_user_ids
        assert "charlie" in timeline_user_ids
        assert "alice" not in timeline_user_ids
    
    def test_blocked_posts_not_in_following_timeline(self):
        """ブロックされたユーザーの投稿はフォロー中タイムラインに表示されないテスト"""
        # フォロー関係を設定（ブロック前）
        self.sns_system.follow_user("charlie", "alice")
        self.sns_system.follow_user("charlie", "bob")
        
        # 投稿を作成
        alice_post = self.sns_system.create_post("alice", "アリスの投稿")
        bob_post = self.sns_system.create_post("bob", "ボブの投稿")
        
        # チャーリーがアリスをブロック
        self.sns_system.block_user("charlie", "alice")
        
        # チャーリーのフォロー中タイムライン（アリスの投稿は表示されない）
        charlie_timeline = self.sns_system.get_following_timeline("charlie")
        timeline_user_ids = [post.user_id for post in charlie_timeline]
        
        assert "bob" in timeline_user_ids
        assert "alice" not in timeline_user_ids
    
    def test_blocked_posts_not_in_hashtag_timeline(self):
        """ブロックされたユーザーの投稿はハッシュタグタイムラインに表示されないテスト"""
        # ハッシュタグ付き投稿を作成
        alice_post = self.sns_system.create_post("alice", "アリスの投稿 #テスト")
        bob_post = self.sns_system.create_post("bob", "ボブの投稿 #テスト")
        charlie_post = self.sns_system.create_post("charlie", "チャーリーの投稿 #テスト")
        
        # アリスがボブをブロック
        self.sns_system.block_user("alice", "bob")
        
        # アリスのハッシュタグタイムライン（ボブの投稿は表示されない）
        alice_hashtag_timeline = self.sns_system.get_hashtag_timeline("テスト", viewer_id="alice")
        timeline_user_ids = [post.user_id for post in alice_hashtag_timeline]
        
        assert "alice" in timeline_user_ids
        assert "charlie" in timeline_user_ids
        assert "bob" not in timeline_user_ids
    
    # === エージェントアダプター経由のテスト ===
    
    def test_agent_block_user(self):
        """エージェント経由のブロック機能テスト"""
        result = self.sns_adapter.agent_block_user(self.alice, self.bob)
        assert result is True
        assert self.sns_adapter.is_agent_blocked(self.alice, self.bob)
    
    def test_agent_unblock_user(self):
        """エージェント経由のブロック解除テスト"""
        self.sns_adapter.agent_block_user(self.alice, self.bob)
        assert self.sns_adapter.is_agent_blocked(self.alice, self.bob)
        
        result = self.sns_adapter.agent_unblock_user(self.alice, self.bob)
        assert result is True
        assert not self.sns_adapter.is_agent_blocked(self.alice, self.bob)
    
    def test_agent_blocked_list(self):
        """エージェントのブロックリスト取得テスト"""
        self.sns_adapter.agent_block_user(self.alice, self.bob)
        self.sns_adapter.agent_block_user(self.alice, self.charlie)
        
        blocked_list = self.sns_adapter.get_agent_blocked_list(self.alice)
        assert "bob" in blocked_list
        assert "charlie" in blocked_list
        assert len(blocked_list) == 2
        
        blocked_count = self.sns_adapter.get_agent_blocked_count(self.alice)
        assert blocked_count == 2
    
    def test_agent_relationship_status_with_block(self):
        """ブロック関係を含むエージェント関係性テスト"""
        # 初期状態
        status = self.sns_adapter.get_agent_relationship_status(self.alice, self.bob)
        assert status["is_blocking"] is False
        assert status["is_blocked_by"] is False
        
        # アリスがボブをブロック
        self.sns_adapter.agent_block_user(self.alice, self.bob)
        
        # アリス視点
        alice_status = self.sns_adapter.get_agent_relationship_status(self.alice, self.bob)
        assert alice_status["is_blocking"] is True
        assert alice_status["is_blocked_by"] is False
        
        # ボブ視点
        bob_status = self.sns_adapter.get_agent_relationship_status(self.bob, self.alice)
        assert bob_status["is_blocking"] is False
        assert bob_status["is_blocked_by"] is True
    
    def test_agent_timeline_with_blocks(self):
        """ブロック制限が適用されたエージェントタイムラインテスト"""
        # 投稿を作成
        self.sns_adapter.agent_post(self.alice, "アリスの投稿")
        self.sns_adapter.agent_post(self.bob, "ボブの投稿")
        self.sns_adapter.agent_post(self.charlie, "チャーリーの投稿")
        
        # アリスがボブをブロック
        self.sns_adapter.agent_block_user(self.alice, self.bob)
        
        # アリスのグローバルタイムライン（ボブの投稿は除外）
        alice_timeline = self.sns_adapter.get_agent_timeline(self.alice, "global")
        timeline_user_ids = [post.user_id for post in alice_timeline]
        
        assert "alice" in timeline_user_ids
        assert "charlie" in timeline_user_ids
        assert "bob" not in timeline_user_ids
    
    def test_agent_hashtag_timeline_with_blocks(self):
        """ブロック制限が適用されたハッシュタグタイムラインテスト"""
        # ハッシュタグ付き投稿を作成
        self.sns_adapter.agent_post(self.alice, "アリスの投稿 #テスト")
        self.sns_adapter.agent_post(self.bob, "ボブの投稿 #テスト")
        
        # アリスがボブをブロック
        self.sns_adapter.agent_block_user(self.alice, self.bob)
        
        # アリス視点のハッシュタグタイムライン
        timeline = self.sns_adapter.get_hashtag_timeline("テスト", viewer_agent=self.alice)
        timeline_user_ids = [post.user_id for post in timeline]
        
        assert "alice" in timeline_user_ids
        assert "bob" not in timeline_user_ids
    
    # === 統計情報のテスト ===
    
    def test_system_stats_includes_blocks(self):
        """システム統計情報にブロック数が含まれるテスト"""
        # 初期状態
        stats = self.sns_system.get_system_stats()
        assert stats["total_blocks"] == 0
        
        # ブロック関係を作成
        self.sns_system.block_user("alice", "bob")
        self.sns_system.block_user("bob", "charlie")
        
        # 統計情報の更新を確認
        stats = self.sns_system.get_system_stats()
        assert stats["total_blocks"] == 2
    
    # === エッジケースのテスト ===
    
    def test_block_after_interactions(self):
        """既存のインタラクション後のブロックテスト"""
        # 投稿、いいね、返信を作成
        post = self.sns_system.create_post("alice", "テスト投稿")
        self.sns_system.like_post("bob", post.post_id)
        self.sns_system.reply_to_post("bob", post.post_id, "返信内容")
        
        # 既存のいいねと返信は残る
        assert self.sns_system.has_liked("bob", post.post_id)
        replies = self.sns_system.get_post_replies(post.post_id)
        assert len(replies) == 1
        
        # ブロック後は新しいインタラクションができない
        self.sns_system.block_user("alice", "bob")
        
        # 新しいいいねと返信は拒否される
        new_post = self.sns_system.create_post("alice", "新しい投稿")
        assert not self.sns_system.like_post("bob", new_post.post_id)
        assert self.sns_system.reply_to_post("bob", new_post.post_id, "返信") is None
    
    def test_unblock_allows_interactions_again(self):
        """ブロック解除後はインタラクションが再び可能になるテスト"""
        post = self.sns_system.create_post("alice", "テスト投稿")
        
        # ブロック
        self.sns_system.block_user("alice", "bob")
        assert not self.sns_system.like_post("bob", post.post_id)
        
        # ブロック解除
        self.sns_system.unblock_user("alice", "bob")
        
        # インタラクションが再び可能
        assert self.sns_system.like_post("bob", post.post_id)
        assert self.sns_system.reply_to_post("bob", post.post_id, "返信内容") is not None 