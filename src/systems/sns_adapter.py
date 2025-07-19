from typing import List, Optional, Dict, Any
from .sns_system import SnsSystem
from ..models.agent import Agent
from ..models.sns import SnsUser, Post, Follow, Like, Reply, Notification, Block, PostVisibility


class SnsAdapter:
    """SNSシステムと既存システムを統合するアダプタークラス"""
    
    def __init__(self, sns_system: SnsSystem):
        self.sns_system = sns_system
    
    # === エージェントとSNSユーザーの統合 ===
    
    def register_agent_as_sns_user(self, agent: Agent, bio: str = "") -> Optional[SnsUser]:
        """エージェントをSNSユーザーとして登録"""
        try:
            return self.sns_system.create_user(
                user_id=agent.agent_id,
                name=agent.name,
                bio=bio
            )
        except ValueError:
            # 既に登録済みの場合は既存ユーザーを返す
            return self.sns_system.get_user(agent.agent_id)
    
    def get_agent_sns_profile(self, agent: Agent) -> Optional[SnsUser]:
        """エージェントのSNSプロフィールを取得"""
        return self.sns_system.get_user(agent.agent_id)
    
    def update_agent_bio(self, agent: Agent, new_bio: str) -> Optional[SnsUser]:
        """エージェントのSNS一言コメントを更新"""
        return self.sns_system.update_user_bio(agent.agent_id, new_bio)
    
    def is_agent_registered(self, agent: Agent) -> bool:
        """エージェントがSNSに登録済みかチェック"""
        return self.sns_system.user_exists(agent.agent_id)
    
    # === エージェント向けSNS操作 ===
    
    def agent_post(self, agent: Agent, content: str, hashtags: Optional[List[str]] = None, 
                   visibility: PostVisibility = PostVisibility.PUBLIC, 
                   allowed_agents: Optional[List[Agent]] = None) -> Optional[Post]:
        """エージェントが投稿する"""
        # SNSユーザーとして未登録の場合は自動登録
        if not self.is_agent_registered(agent):
            self.register_agent_as_sns_user(agent)
        
        # 許可エージェントリストをユーザーIDリストに変換
        allowed_users = None
        if allowed_agents:
            # 許可エージェントも自動登録
            for allowed_agent in allowed_agents:
                if not self.is_agent_registered(allowed_agent):
                    self.register_agent_as_sns_user(allowed_agent)
            allowed_users = [a.agent_id for a in allowed_agents]
        
        return self.sns_system.create_post(
            agent.agent_id, content, hashtags, visibility, allowed_users
        )
    
    def agent_follow(self, follower_agent: Agent, target_agent: Agent) -> bool:
        """エージェントが他のエージェントをフォロー"""
        # 両方のエージェントがSNSに登録されているかチェック
        if not self.is_agent_registered(follower_agent):
            self.register_agent_as_sns_user(follower_agent)
        if not self.is_agent_registered(target_agent):
            self.register_agent_as_sns_user(target_agent)
        
        return self.sns_system.follow_user(follower_agent.agent_id, target_agent.agent_id)
    
    def agent_unfollow(self, follower_agent: Agent, target_agent: Agent) -> bool:
        """エージェントがフォローを解除"""
        return self.sns_system.unfollow_user(follower_agent.agent_id, target_agent.agent_id)
    
    def agent_like_post(self, agent: Agent, post_id: str) -> bool:
        """エージェントが投稿にいいね"""
        if not self.is_agent_registered(agent):
            self.register_agent_as_sns_user(agent)
        
        return self.sns_system.like_post(agent.agent_id, post_id)
    
    def agent_unlike_post(self, agent: Agent, post_id: str) -> bool:
        """エージェントがいいねを解除"""
        return self.sns_system.unlike_post(agent.agent_id, post_id)
    
    def agent_reply_to_post(self, agent: Agent, post_id: str, content: str) -> Optional[Reply]:
        """エージェントが投稿に返信"""
        if not self.is_agent_registered(agent):
            self.register_agent_as_sns_user(agent)
        
        return self.sns_system.reply_to_post(agent.agent_id, post_id, content)
    
    # === ブロック機能 ===
    
    def agent_block_user(self, blocker_agent: Agent, target_agent: Agent) -> bool:
        """エージェントが他のエージェントをブロック"""
        # 両方のエージェントがSNSに登録されているかチェック
        if not self.is_agent_registered(blocker_agent):
            self.register_agent_as_sns_user(blocker_agent)
        if not self.is_agent_registered(target_agent):
            self.register_agent_as_sns_user(target_agent)
        
        return self.sns_system.block_user(blocker_agent.agent_id, target_agent.agent_id)
    
    def agent_unblock_user(self, blocker_agent: Agent, target_agent: Agent) -> bool:
        """エージェントがブロックを解除"""
        return self.sns_system.unblock_user(blocker_agent.agent_id, target_agent.agent_id)
    
    def is_agent_blocked(self, blocker_agent: Agent, target_agent: Agent) -> bool:
        """エージェント間のブロック関係をチェック"""
        return self.sns_system.is_blocked(blocker_agent.agent_id, target_agent.agent_id)
    
    def get_agent_blocked_list(self, agent: Agent, limit: int = 100) -> List[str]:
        """エージェントがブロックしているユーザーリストを取得"""
        return self.sns_system.get_blocked_list(agent.agent_id, limit)
    
    def get_agent_blocked_count(self, agent: Agent) -> int:
        """エージェントがブロックしているユーザー数を取得"""
        return self.sns_system.get_blocked_count(agent.agent_id)
    
    # === プライベート投稿関連のヘルパーメソッド ===
    
    def agent_create_private_post(self, agent: Agent, content: str, hashtags: Optional[List[str]] = None) -> Optional[Post]:
        """エージェントがプライベート投稿を作成"""
        return self.agent_post(agent, content, hashtags, PostVisibility.PRIVATE)
    
    def agent_create_followers_only_post(self, agent: Agent, content: str, hashtags: Optional[List[str]] = None) -> Optional[Post]:
        """エージェントがフォロワー限定投稿を作成"""
        return self.agent_post(agent, content, hashtags, PostVisibility.FOLLOWERS_ONLY)
    
    def agent_create_mutual_follows_post(self, agent: Agent, content: str, hashtags: Optional[List[str]] = None) -> Optional[Post]:
        """エージェントが相互フォロー限定投稿を作成"""
        return self.agent_post(agent, content, hashtags, PostVisibility.MUTUAL_FOLLOWS_ONLY)
    
    def agent_create_specified_users_post(self, agent: Agent, content: str, 
                                        allowed_agents: List[Agent], 
                                        hashtags: Optional[List[str]] = None) -> Optional[Post]:
        """エージェントが指定ユーザー限定投稿を作成"""
        return self.agent_post(agent, content, hashtags, PostVisibility.SPECIFIED_USERS, allowed_agents)
    
    def get_agent_posts_by_visibility(self, agent: Agent, visibility: PostVisibility, limit: int = 50) -> List[Post]:
        """エージェントの特定可視性レベルの投稿を取得"""
        user_posts = self.sns_system.get_user_posts(agent.agent_id, limit=1000)  # 多めに取得
        filtered_posts = [post for post in user_posts if post.visibility == visibility]
        return filtered_posts[:limit]
    
    def get_agent_visibility_stats(self, agent: Agent) -> Dict[str, int]:
        """エージェントの可視性別投稿統計を取得"""
        user_posts = self.sns_system.get_user_posts(agent.agent_id, limit=1000)
        visibility_counts = {}
        
        for post in user_posts:
            visibility = post.visibility.value
            visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1
        
        return visibility_counts
    
    # === エージェント向け情報取得 ===
    
    def get_agent_timeline(self, agent: Agent, timeline_type: str = "global", limit: int = 50) -> List[Post]:
        """エージェントのタイムラインを取得
        
        Args:
            agent: エージェント
            timeline_type: タイムラインタイプ ("global", "following", "user")
            limit: 取得件数制限
        """
        if timeline_type == "following":
            return self.sns_system.get_following_timeline(agent.agent_id, limit)
        elif timeline_type == "user":
            return self.sns_system.get_user_posts(agent.agent_id, limit)
        else:  # "global"
            return self.sns_system.get_global_timeline(viewer_id=agent.agent_id, limit=limit)
    
    def get_agent_notifications(self, agent: Agent, unread_only: bool = False, limit: int = 50) -> List[Notification]:
        """エージェントの通知を取得"""
        return self.sns_system.get_user_notifications(agent.agent_id, unread_only, limit)
    
    def get_agent_unread_count(self, agent: Agent) -> int:
        """エージェントの未読通知数を取得"""
        return self.sns_system.get_unread_notifications_count(agent.agent_id)
    
    def mark_agent_notification_read(self, agent: Agent, notification_id: str) -> bool:
        """エージェントの通知を既読にマーク"""
        return self.sns_system.mark_notification_as_read(notification_id)
    
    def get_agent_social_stats(self, agent: Agent) -> Dict[str, Any]:
        """エージェントのソーシャル統計を取得"""
        user_posts = self.sns_system.get_user_posts(agent.agent_id)
        followers_count = self.sns_system.get_followers_count(agent.agent_id)
        following_count = self.sns_system.get_following_count(agent.agent_id)
        
        # 投稿の総いいね数を計算
        total_likes = sum(
            self.sns_system.get_post_likes_count(post.post_id) 
            for post in user_posts
        )
        
        # 投稿の総返信数を計算
        total_replies = sum(
            self.sns_system.get_post_replies_count(post.post_id) 
            for post in user_posts
        )
        
        return {
            "posts_count": len(user_posts),
            "followers_count": followers_count,
            "following_count": following_count,
            "total_likes_received": total_likes,
            "total_replies_received": total_replies,
            "unread_notifications": self.get_agent_unread_count(agent)
        }
    
    # === ハッシュタグ機能 ===
    
    def get_hashtag_timeline(self, hashtag: str, viewer_agent: Optional[Agent] = None, limit: int = 50) -> List[Post]:
        """ハッシュタグタイムラインを取得"""
        viewer_id = viewer_agent.agent_id if viewer_agent else None
        return self.sns_system.get_hashtag_timeline(hashtag, viewer_id=viewer_id, limit=limit)
    
    def get_trending_hashtags(self, limit: int = 10) -> List[Dict[str, Any]]:
        """トレンドハッシュタグを取得（投稿数順）"""
        hashtag_counts = {}
        
        # 全投稿からハッシュタグを集計
        for post in self.sns_system.posts.values():
            for hashtag in post.hashtags:
                hashtag_counts[hashtag] = hashtag_counts.get(hashtag, 0) + 1
        
        # 投稿数順でソート
        trending = sorted(
            hashtag_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:limit]
        
        return [
            {"hashtag": hashtag, "count": count} 
            for hashtag, count in trending
        ]
    
    # === 検索機能 ===
    
    def search_users(self, query: str, limit: int = 20) -> List[SnsUser]:
        """ユーザー検索（名前での部分一致）"""
        matching_users = []
        query_lower = query.lower()
        
        for user in self.sns_system.users.values():
            if (query_lower in user.name.lower() or 
                query_lower in user.bio.lower()):
                matching_users.append(user)
        
        return matching_users[:limit]
    
    def search_posts(self, query: str, limit: int = 50) -> List[Post]:
        """投稿検索（内容での部分一致）"""
        matching_posts = []
        query_lower = query.lower()
        
        for post in self.sns_system.posts.values():
            if query_lower in post.content.lower():
                matching_posts.append(post)
        
        # 新しい順でソート
        matching_posts.sort(key=lambda p: p.created_at, reverse=True)
        return matching_posts[:limit]
    
    # === エージェント向けヘルパーメソッド ===
    
    def get_post_with_interactions(self, post_id: str) -> Optional[Dict[str, Any]]:
        """投稿とそのインタラクション情報を取得"""
        post = self.sns_system.get_post(post_id)
        if not post:
            return None
        
        likes_count = self.sns_system.get_post_likes_count(post_id)
        replies_count = self.sns_system.get_post_replies_count(post_id)
        replies = self.sns_system.get_post_replies(post_id, limit=10)
        
        return {
            "post": post,
            "likes_count": likes_count,
            "replies_count": replies_count,
            "recent_replies": replies,
            "author": self.sns_system.get_user(post.user_id)
        }
    
    def get_agent_feed_with_details(self, agent: Agent, timeline_type: str = "global", limit: int = 20) -> List[Dict[str, Any]]:
        """詳細情報付きのエージェントフィードを取得"""
        posts = self.get_agent_timeline(agent, timeline_type, limit)
        
        feed = []
        for post in posts:
            post_details = self.get_post_with_interactions(post.post_id)
            if post_details:
                # エージェントがこの投稿をいいねしているかチェック
                post_details["liked_by_agent"] = self.sns_system.has_liked(agent.agent_id, post.post_id)
                feed.append(post_details)
        
        return feed
    
    def get_mutual_follows(self, agent1: Agent, agent2: Agent) -> bool:
        """2つのエージェントが相互フォローしているかチェック"""
        return (self.sns_system.is_following(agent1.agent_id, agent2.agent_id) and 
                self.sns_system.is_following(agent2.agent_id, agent1.agent_id))
    
    def get_agent_relationship_status(self, agent: Agent, target_agent: Agent) -> Dict[str, bool]:
        """エージェント間の関係性を取得"""
        return {
            "is_following": self.sns_system.is_following(agent.agent_id, target_agent.agent_id),
            "is_followed_by": self.sns_system.is_following(target_agent.agent_id, agent.agent_id),
            "is_mutual": self.get_mutual_follows(agent, target_agent),
            "is_blocking": self.sns_system.is_blocked(agent.agent_id, target_agent.agent_id),
            "is_blocked_by": self.sns_system.is_blocked(target_agent.agent_id, agent.agent_id)
        } 