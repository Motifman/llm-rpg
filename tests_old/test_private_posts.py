import pytest
from src.systems.sns_system import SnsSystem
from src.systems.sns_adapter import SnsAdapter
from src.models.agent import Agent
from src.models.sns import PostVisibility


class TestPrivatePosts:
    """プライベート投稿機能のテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行される初期化処理"""
        self.sns_system = SnsSystem()
        self.sns_adapter = SnsAdapter(self.sns_system)
        
        # テスト用エージェントを作成
        self.alice = Agent("alice", "アリス")
        self.bob = Agent("bob", "ボブ")
        self.charlie = Agent("charlie", "チャーリー")
        self.david = Agent("david", "デイビッド")
        
        # エージェントをSNSに登録
        self.sns_adapter.register_agent_as_sns_user(self.alice)
        self.sns_adapter.register_agent_as_sns_user(self.bob)
        self.sns_adapter.register_agent_as_sns_user(self.charlie)
        self.sns_adapter.register_agent_as_sns_user(self.david)
        
        # フォロー関係を設定
        self.sns_adapter.agent_follow(self.bob, self.alice)      # Bob → Alice
        self.sns_adapter.agent_follow(self.alice, self.bob)      # Alice → Bob (相互)
        self.sns_adapter.agent_follow(self.charlie, self.alice)  # Charlie → Alice (一方向)
    
    # === 投稿可視性レベルのテスト ===
    
    def test_public_post_creation(self):
        """パブリック投稿作成のテスト"""
        post = self.sns_adapter.agent_post(self.alice, "パブリック投稿です")
        
        assert post is not None
        assert post.visibility == PostVisibility.PUBLIC
        assert post.is_public()
        assert post.get_visibility_label() == "🌍 パブリック"
    
    def test_private_post_creation(self):
        """プライベート投稿作成のテスト"""
        post = self.sns_adapter.agent_create_private_post(self.alice, "プライベートメモです")
        
        assert post is not None
        assert post.visibility == PostVisibility.PRIVATE
        assert post.is_private()
        assert post.get_visibility_label() == "🔒 プライベート"
    
    def test_followers_only_post_creation(self):
        """フォロワー限定投稿作成のテスト"""
        post = self.sns_adapter.agent_create_followers_only_post(self.alice, "フォロワーの皆さんへ")
        
        assert post is not None
        assert post.visibility == PostVisibility.FOLLOWERS_ONLY
        assert post.is_followers_only()
        assert post.get_visibility_label() == "👥 フォロワー限定"
    
    def test_mutual_follows_only_post_creation(self):
        """相互フォロー限定投稿作成のテスト"""
        post = self.sns_adapter.agent_create_mutual_follows_post(self.alice, "相互フォローの友達へ")
        
        assert post is not None
        assert post.visibility == PostVisibility.MUTUAL_FOLLOWS_ONLY
        assert post.is_mutual_follows_only()
        assert post.get_visibility_label() == "🤝 相互フォロー限定"
    
    def test_specified_users_post_creation(self):
        """指定ユーザー限定投稿作成のテスト"""
        post = self.sns_adapter.agent_create_specified_users_post(
            self.alice, "ボブとチャーリーだけに", [self.bob, self.charlie]
        )
        
        assert post is not None
        assert post.visibility == PostVisibility.SPECIFIED_USERS
        assert post.is_specified_users_only()
        assert post.get_visibility_label() == "🎯 指定ユーザー限定"
        assert "bob" in post.allowed_users
        assert "charlie" in post.allowed_users
        assert "david" not in post.allowed_users
    
    def test_specified_users_post_with_empty_list(self):
        """指定ユーザーが空の場合の投稿作成テスト"""
        post = self.sns_system.create_post(
            "alice", "指定ユーザーなし", visibility=PostVisibility.SPECIFIED_USERS, allowed_users=[]
        )
        
        assert post is None  # 空のリストでは作成失敗
    
    def test_specified_users_post_with_nonexistent_users(self):
        """存在しないユーザーを指定した場合のテスト"""
        post = self.sns_system.create_post(
            "alice", "存在しないユーザー指定", 
            visibility=PostVisibility.SPECIFIED_USERS, 
            allowed_users=["nonexistent1", "bob", "nonexistent2"]
        )
        
        assert post is not None
        assert "bob" in post.allowed_users
        assert "nonexistent1" not in post.allowed_users
        assert "nonexistent2" not in post.allowed_users
    
    # === 投稿可視性チェックのテスト ===
    
    def test_public_post_visibility(self):
        """パブリック投稿の可視性テスト"""
        post = self.sns_adapter.agent_post(self.alice, "パブリック投稿")
        
        # 全員が閲覧可能
        assert self.sns_system._is_post_visible(post, "alice")
        assert self.sns_system._is_post_visible(post, "bob")
        assert self.sns_system._is_post_visible(post, "charlie")
        assert self.sns_system._is_post_visible(post, "david")
    
    def test_private_post_visibility(self):
        """プライベート投稿の可視性テスト"""
        post = self.sns_adapter.agent_create_private_post(self.alice, "プライベート投稿")
        
        # 本人のみ閲覧可能
        assert self.sns_system._is_post_visible(post, "alice")
        assert not self.sns_system._is_post_visible(post, "bob")
        assert not self.sns_system._is_post_visible(post, "charlie")
        assert not self.sns_system._is_post_visible(post, "david")
    
    def test_followers_only_post_visibility(self):
        """フォロワー限定投稿の可視性テスト"""
        post = self.sns_adapter.agent_create_followers_only_post(self.alice, "フォロワー限定投稿")
        
        # フォロワーのみ閲覧可能
        assert self.sns_system._is_post_visible(post, "alice")  # 本人
        assert self.sns_system._is_post_visible(post, "bob")    # フォロワー
        assert self.sns_system._is_post_visible(post, "charlie") # フォロワー
        assert not self.sns_system._is_post_visible(post, "david") # 非フォロワー
    
    def test_mutual_follows_only_post_visibility(self):
        """相互フォロー限定投稿の可視性テスト"""
        post = self.sns_adapter.agent_create_mutual_follows_post(self.alice, "相互フォロー限定投稿")
        
        # 相互フォローのみ閲覧可能
        assert self.sns_system._is_post_visible(post, "alice")   # 本人
        assert self.sns_system._is_post_visible(post, "bob")     # 相互フォロー
        assert not self.sns_system._is_post_visible(post, "charlie") # 一方向フォロー
        assert not self.sns_system._is_post_visible(post, "david")   # フォロー関係なし
    
    def test_specified_users_post_visibility(self):
        """指定ユーザー限定投稿の可視性テスト"""
        post = self.sns_adapter.agent_create_specified_users_post(
            self.alice, "指定ユーザー限定投稿", [self.bob, self.charlie]
        )
        
        # 指定されたユーザーのみ閲覧可能
        assert self.sns_system._is_post_visible(post, "alice")   # 本人
        assert self.sns_system._is_post_visible(post, "bob")     # 指定ユーザー
        assert self.sns_system._is_post_visible(post, "charlie") # 指定ユーザー
        assert not self.sns_system._is_post_visible(post, "david")   # 指定外ユーザー
    
    # === タイムラインでの可視性フィルタリングテスト ===
    
    def test_global_timeline_with_mixed_visibility(self):
        """様々な可視性レベルの投稿が混在するグローバルタイムラインのテスト"""
        # 様々な可視性の投稿を作成
        public_post = self.sns_adapter.agent_post(self.alice, "パブリック投稿")
        private_post = self.sns_adapter.agent_create_private_post(self.alice, "プライベート投稿")
        followers_post = self.sns_adapter.agent_create_followers_only_post(self.alice, "フォロワー限定投稿")
        
        # ボブのタイムライン（アリスのフォロワー）
        bob_timeline = self.sns_adapter.get_agent_timeline(self.bob, "global")
        bob_post_ids = [post.post_id for post in bob_timeline]
        
        assert public_post.post_id in bob_post_ids     # パブリック投稿は表示
        assert private_post.post_id not in bob_post_ids # プライベート投稿は非表示
        assert followers_post.post_id in bob_post_ids   # フォロワー限定投稿は表示
        
        # デイビッドのタイムライン（フォロワーではない）
        david_timeline = self.sns_adapter.get_agent_timeline(self.david, "global")
        david_post_ids = [post.post_id for post in david_timeline]
        
        assert public_post.post_id in david_post_ids      # パブリック投稿は表示
        assert private_post.post_id not in david_post_ids # プライベート投稿は非表示
        assert followers_post.post_id not in david_post_ids # フォロワー限定投稿は非表示
    
    def test_following_timeline_with_private_posts(self):
        """プライベート投稿を含むフォロー中タイムラインのテスト"""
        # アリスの様々な投稿
        public_post = self.sns_adapter.agent_post(self.alice, "パブリック投稿")
        mutual_post = self.sns_adapter.agent_create_mutual_follows_post(self.alice, "相互フォロー限定投稿")
        
        # ボブのフォロー中タイムライン（相互フォロー）
        bob_timeline = self.sns_adapter.get_agent_timeline(self.bob, "following")
        bob_post_ids = [post.post_id for post in bob_timeline]
        
        assert public_post.post_id in bob_post_ids
        assert mutual_post.post_id in bob_post_ids
        
        # チャーリーのフォロー中タイムライン（一方向フォロー）
        charlie_timeline = self.sns_adapter.get_agent_timeline(self.charlie, "following")
        charlie_post_ids = [post.post_id for post in charlie_timeline]
        
        assert public_post.post_id in charlie_post_ids
        assert mutual_post.post_id not in charlie_post_ids  # 相互フォローではないので非表示
    
    def test_hashtag_timeline_with_private_posts(self):
        """プライベート投稿を含むハッシュタグタイムラインのテスト"""
        # ハッシュタグ付きの様々な投稿
        public_post = self.sns_adapter.agent_post(self.alice, "パブリック投稿 #テスト")
        private_post = self.sns_adapter.agent_create_private_post(self.alice, "プライベート投稿 #テスト")
        followers_post = self.sns_adapter.agent_create_followers_only_post(self.alice, "フォロワー限定 #テスト")
        
        # ボブ視点のハッシュタグタイムライン
        bob_hashtag_timeline = self.sns_adapter.get_hashtag_timeline("テスト", viewer_agent=self.bob)
        bob_post_ids = [post.post_id for post in bob_hashtag_timeline]
        
        assert public_post.post_id in bob_post_ids
        assert private_post.post_id not in bob_post_ids
        assert followers_post.post_id in bob_post_ids
        
        # 閲覧者指定なしの場合（パブリックのみ）
        public_hashtag_timeline = self.sns_adapter.get_hashtag_timeline("テスト")
        public_post_ids = [post.post_id for post in public_hashtag_timeline]
        
        assert public_post.post_id in public_post_ids
        assert private_post.post_id not in public_post_ids
        assert followers_post.post_id not in public_post_ids
    
    # === インタラクション制限のテスト ===
    
    def test_like_private_post(self):
        """プライベート投稿へのいいねテスト"""
        private_post = self.sns_adapter.agent_create_private_post(self.alice, "プライベート投稿")
        
        # 本人はいいね可能
        result = self.sns_adapter.agent_like_post(self.alice, private_post.post_id)
        assert result is True
        
        # 他人はいいね不可
        result = self.sns_adapter.agent_like_post(self.bob, private_post.post_id)
        assert result is False
    
    def test_reply_to_followers_only_post(self):
        """フォロワー限定投稿への返信テスト"""
        followers_post = self.sns_adapter.agent_create_followers_only_post(self.alice, "フォロワー限定投稿")
        
        # フォロワーは返信可能
        reply = self.sns_adapter.agent_reply_to_post(self.bob, followers_post.post_id, "返信です")
        assert reply is not None
        
        # 非フォロワーは返信不可
        reply = self.sns_adapter.agent_reply_to_post(self.david, followers_post.post_id, "返信試行")
        assert reply is None
    
    def test_like_specified_users_post(self):
        """指定ユーザー限定投稿へのいいねテスト"""
        specified_post = self.sns_adapter.agent_create_specified_users_post(
            self.alice, "指定ユーザー限定投稿", [self.bob]
        )
        
        # 指定ユーザーはいいね可能
        result = self.sns_adapter.agent_like_post(self.bob, specified_post.post_id)
        assert result is True
        
        # 指定外ユーザーはいいね不可
        result = self.sns_adapter.agent_like_post(self.charlie, specified_post.post_id)
        assert result is False
    
    # === 統計・管理機能のテスト ===
    
    def test_agent_visibility_stats(self):
        """エージェントの可視性別投稿統計テスト"""
        # 様々な可視性の投稿を作成
        self.sns_adapter.agent_post(self.alice, "パブリック1")
        self.sns_adapter.agent_post(self.alice, "パブリック2")
        self.sns_adapter.agent_create_private_post(self.alice, "プライベート1")
        self.sns_adapter.agent_create_followers_only_post(self.alice, "フォロワー限定1")
        
        stats = self.sns_adapter.get_agent_visibility_stats(self.alice)
        
        assert stats.get("public", 0) == 2
        assert stats.get("private", 0) == 1
        assert stats.get("followers_only", 0) == 1
        assert stats.get("mutual_follows_only", 0) == 0
    
    def test_get_agent_posts_by_visibility(self):
        """可視性別投稿取得テスト"""
        # 様々な投稿を作成
        public_post = self.sns_adapter.agent_post(self.alice, "パブリック投稿")
        private_post = self.sns_adapter.agent_create_private_post(self.alice, "プライベート投稿")
        
        # プライベート投稿のみ取得
        private_posts = self.sns_adapter.get_agent_posts_by_visibility(self.alice, PostVisibility.PRIVATE)
        assert len(private_posts) == 1
        assert private_posts[0].post_id == private_post.post_id
        
        # パブリック投稿のみ取得
        public_posts = self.sns_adapter.get_agent_posts_by_visibility(self.alice, PostVisibility.PUBLIC)
        assert len(public_posts) == 1
        assert public_posts[0].post_id == public_post.post_id
    
    def test_system_stats_with_visibility(self):
        """可視性別投稿数を含むシステム統計テスト"""
        # 様々な投稿を作成
        self.sns_adapter.agent_post(self.alice, "パブリック1")
        self.sns_adapter.agent_post(self.bob, "パブリック2")
        self.sns_adapter.agent_create_private_post(self.alice, "プライベート1")
        self.sns_adapter.agent_create_followers_only_post(self.charlie, "フォロワー限定1")
        
        stats = self.sns_system.get_system_stats()
        
        assert stats["total_posts"] == 4
        assert stats["posts_by_visibility"]["public"] == 2
        assert stats["posts_by_visibility"]["private"] == 1
        assert stats["posts_by_visibility"]["followers_only"] == 1
    
    # === エラーハンドリングのテスト ===
    
    def test_create_specified_post_with_unregistered_agents(self):
        """未登録エージェントを指定した投稿作成テスト"""
        # 新しい未登録エージェント
        eve = Agent("eve", "イブ")
        
        # 未登録エージェントを含む指定ユーザー投稿
        post = self.sns_adapter.agent_create_specified_users_post(
            self.alice, "未登録ユーザーを含む投稿", [self.bob, eve]
        )
        
        assert post is not None
        assert "bob" in post.allowed_users
        assert "eve" in post.allowed_users  # 自動登録される
        
        # イブがSNSに自動登録されたかチェック
        assert self.sns_adapter.is_agent_registered(eve)
    
    def test_visibility_with_block_interaction(self):
        """ブロック機能とプライベート投稿の組み合わせテスト"""
        # アリスがフォロワー限定投稿を作成
        followers_post = self.sns_adapter.agent_create_followers_only_post(self.alice, "フォロワー限定投稿")
        
        # ボブ（フォロワー）は通常閲覧可能
        assert self.sns_system._is_post_visible(followers_post, "bob")
        
        # アリスがボブをブロック
        self.sns_adapter.agent_block_user(self.alice, self.bob)
        
        # ブロック後は閲覧不可（ブロック制限が優先）
        assert not self.sns_system._is_post_visible(followers_post, "bob") 