import uuid
import time
import logging
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from game.sns.new_sns_data import SnsUser, Post, Follow, Like, Reply, Notification, Block, Mention
from game.player.player import Player
from game.enums import NotificationType, PostVisibility
from game.core.database import Database

logger = logging.getLogger(__name__)


class SnsManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = Database(self.db_path)
        self.db_conn = self.db.conn
        self.cursor = self.db_conn.cursor()
        logger.info(f"Database connection established successfully to {self.db_path}")

        try:
            self._create_table()
        except Exception as e:
            logger.error(f"Failed to create table: {e}")
            raise e
        logger.info(f"SnsManager initialized with db_path: {self.db_path}")

    def _create_table(self):
        try:
            self.db_conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id   TEXT PRIMARY KEY,
                    name      TEXT NOT NULL,
                    bio       TEXT DEFAULT '',
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS posts (
                    post_id   TEXT PRIMARY KEY,
                    user_id   TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    content   TEXT NOT NULL,
                    parent_post_id TEXT DEFAULT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                    visibility TEXT NOT NULL DEFAULT 'public',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    CHECK (visibility IN ('public', 'followers_only', 'mutual_follows_only', 'specified_users_only', 'private'))
                );

                CREATE TABLE IF NOT EXISTS post_hashtags (
                    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                    hashtag TEXT NOT NULL,
                    PRIMARY KEY (post_id, hashtag)
                );                

                CREATE TABLE IF NOT EXISTS post_allowed_users (
                    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                    allowed_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    PRIMARY KEY (post_id, allowed_user_id)
                );

                CREATE TABLE IF NOT EXISTS follows (
                    follower_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    following_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (follower_id, following_id)
                );
                CREATE INDEX idx_follows_following_id ON follows(following_id);

                CREATE TABLE IF NOT EXISTS blocks (
                    blocker_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    blocked_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (blocker_id, blocked_id)
                );

                CREATE TABLE IF NOT EXISTS likes (
                    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (post_id, user_id)
                );
                CREATE INDEX idx_likes_user_id ON likes(user_id);

                CREATE TABLE IF NOT EXISTS mentions (
                    mention_id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                    mentioner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    mentioned_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL
                )
                CREATE INDEX idx_mentions_mentioned_user_id ON mentions(mentioned_user_id);

                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id     TEXT PRIMARY KEY,
                    user_id             TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    actor_id            TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    post_id             TEXT DEFAULT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                    notification_type   TEXT NOT NULL CHECK (notification_type IN ('follow', 'like', 'reply', 'mention')),
                    is_read             INTEGER NOT NULL DEFAULT 0,
                    created_at          INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_notifications_user_status ON notifications(user_id, is_read);
                """
            )
            self.db_conn.commit()
            logger.info(f"SnsManager tables and indexes created")
        except Exception as e:
            logger.error(f"Failed to create table or indexes: {e}")
            self.db_conn.rollback()
            raise e
    
    def __del__(self):
        if getattr(self, "db", None):
            self.db.close()
            
    def create_user(self, user_id: str, name: str, bio: str = "") -> SnsUser:
        """新しいユーザーを作成"""
        now = int(time.time())
        self.cursor.execute(
            """
            INSERT INTO users (user_id, name, bio, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, name, bio, now)
        )
        self.db_conn.commit()
        return SnsUser(user_id=user_id, name=name, bio=bio, created_at=now)
    
    def get_user(self, user_id: str) -> Optional[SnsUser]:
        """ユーザーを取得"""
        self.cursor.execute(
            """
            SELECT user_id, name, bio, created_at
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        )
        row = self.cursor.fetchone()
        if row:
            return SnsUser(user_id=row[0], name=row[1], bio=row[2], created_at=row[3])
        return None
    
    def update_user_bio(self, user_id: str, new_bio: str) -> Optional[SnsUser]:
        """ユーザーの一言コメントを更新"""
        self.cursor.execute(
            """
            UPDATE users
            SET bio = ?
            WHERE user_id = ?
            """,
            (new_bio, user_id)
        )
        self.db_conn.commit()
        return self.get_user(user_id)
    
    def user_exists(self, user_id: str) -> bool:
        """ユーザーが存在するかチェック"""
        self.cursor.execute(
            """
            SELECT EXISTS(
                SELECT 1
                FROM users
                WHERE user_id = ?
            )
            """,
            (user_id,)
        )
        return bool(self.cursor.fetchone()[0])
    
    # === 投稿機能 ===
    def _extract_hashtags_from_content(self, content: str) -> List[str]:
        """投稿内容からハッシュタグを抽出"""
        import re
        hashtag_pattern = r'#[a-zA-Z0-9_@\-\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]+'
        return re.findall(hashtag_pattern, content)

    def _extract_mentions_from_content(self, content: str) -> List[str]:
        """投稿/返信内容からメンション（@ユーザー名）を抽出"""
        import re
        mention_pattern = r'@(\w+)'
        return re.findall(mention_pattern, content)
    
    def create_post(self, user_id: str, content: str, hashtags: Optional[List[str]] = None, 
                   visibility: PostVisibility = PostVisibility.PUBLIC, 
                   allowed_users: Optional[List[str]] = None) -> Optional[Post]:
        """新しい投稿を作成"""
        if not self.user_exists(user_id):
            return None
        
        # 投稿内容からハッシュタグを自動抽出
        extracted_hashtags = self._extract_hashtags_from_content(content)
        if extracted_hashtags:
            all_hashtags = list(set(hashtags or []) + set(extracted_hashtags))
        
        # メンションは難しいので後回し
        # 投稿内容からメンションを自動抽出
        # extracted_mentions = self._extract_mentions_from_content(content)
        # if extracted_mentions:
        #     all_mentions = list(set(mentions or []) + set(extracted_mentions))

        now = int(time.time())
        post_id = str(uuid.uuid4())
        mention_id = str(uuid.uuid4())
        with self.db.transaction("IMMEDIATE"):
            # 投稿を作成
            self.cursor.execute(
                """
                INSERT INTO posts (post_id, user_id, content, visibility, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (post_id, user_id, content, visibility, now, now)
            )
            # ハッシュタグを作成
            hashtag_data = [(post_id, hashtag) for hashtag in all_hashtags]
            self.cursor.executemany(
                """
                INSERT INTO post_hashtags (post_id, hashtag)
                VALUES (?, ?)
                """,
                hashtag_data
            )
            # # メンションを作成
            # mention_data = [(mention_id, post_id, user_id, mentioned_user_id, now) for mentioned_user_id in mentions]
            # self.cursor.executemany(
            #     """
            #     INSERT INTO mentions (mention_id, post_id, mentioner_user_id, mentioned_user_id, created_at)
            #     VALUES (?, ?, ?, ?)
            #     """,
            #     mention_data
            # )
            # # メンション通知を作成
            # notification_data = [(post_id, user_id, user_id, NotificationType.MENTION.value, 0, now) for mention in mentions]
            # self.cursor.executemany(
            #     """
            #     INSERT INTO notifications (post_id, user_id, actor_id, notification_type, is_read, created_at)
            #     VALUES (?, ?, ?, ?, ?, ?)
            #     """,
            #     notification_data
            # )
        self.db_conn.commit()
        return Post(post_id=post_id, user_id=user_id, content=content, visibility=visibility, created_at=now, updated_at=now)
    
    def create_post(self, user_id: str, content: str, hashtags: Optional[List[str]] = None, 
                   visibility: PostVisibility = PostVisibility.PUBLIC, 
                   allowed_users: Optional[List[str]] = None) -> Optional[Post]:
        """新しい投稿を作成"""
        if not self.user_exists(user_id):
            return None
        
        if visibility == PostVisibility.SPECIFIED_USERS:
            if not allowed_users:
                return None
            valid_users = [uid for uid in allowed_users if self.user_exists(uid)]
            if not valid_users:
                return None
            allowed_users = valid_users
        
        post = Post.create(
            user_id=user_id, 
            content=content, 
            hashtags=hashtags,
            visibility=visibility,
            allowed_users=allowed_users
        )
        
        # 投稿内容からハッシュタグを自動抽出（Postから移植した内部実装）
        extracted_hashtags = self._extract_hashtags_from_content(content)
        if extracted_hashtags:
            all_hashtags = list(set((hashtags or []) + extracted_hashtags))
            from dataclasses import replace
            post = replace(post, hashtags=all_hashtags)
        
        self.posts[post.post_id] = post
        
        # メンション処理（投稿がパブリックまたは適切な可視性を持つ場合のみ）
        if post.visibility in [PostVisibility.PUBLIC, PostVisibility.FOLLOWERS_ONLY, PostVisibility.MUTUAL_FOLLOWS_ONLY]:
            self._process_mentions_in_content(content, user_id, post.post_id)
        
        return post
    
    def get_post(self, post_id: str) -> Optional[Post]:
        """投稿を取得"""
        return self.posts.get(post_id)
    
    def get_user_posts(self, user_id: str, limit: int = 50) -> List[Post]:
        """特定のユーザーの投稿を取得"""
        user_posts = [post for post in self.posts.values() if post.user_id == user_id]
        user_posts.sort(key=lambda p: p.created_at, reverse=True)
        return user_posts[:limit]
    
    # === タイムライン機能 ===
    
    def get_global_timeline(self, viewer_id: Optional[str] = None, limit: int = 50) -> List[Post]:
        """グローバルタイムライン（全体の最新投稿）を取得"""
        all_posts = list(self.posts.values())
        
        # 可視性制限を適用（viewer_idが指定されている場合）
        if viewer_id:
            filtered_posts = [
                post for post in all_posts 
                if self._is_post_visible(post, viewer_id)
            ]
        else:
            # 閲覧者が指定されていない場合はパブリック投稿のみ
            filtered_posts = [
                post for post in all_posts 
                if post.visibility == PostVisibility.PUBLIC
            ]
        
        filtered_posts.sort(key=lambda p: p.created_at, reverse=True)
        return filtered_posts[:limit]
    
    def get_following_timeline(self, user_id: str, limit: int = 50) -> List[Post]:
        """フォロー中のユーザーのタイムラインを取得"""
        following_ids = self.get_following_list(user_id)
        following_posts = [
            post for post in self.posts.values() 
            if post.user_id in following_ids and self._is_post_visible(post, user_id)
        ]
        following_posts.sort(key=lambda p: p.created_at, reverse=True)
        return following_posts[:limit]
    
    def get_hashtag_timeline(self, hashtag: str, viewer_id: Optional[str] = None, limit: int = 50) -> List[Post]:
        """特定のハッシュタグの投稿を取得"""
        # ハッシュタグの正規化（#記号の有無を統一）
        normalized_hashtag = hashtag if hashtag.startswith('#') else f'#{hashtag}'
        
        hashtag_posts = [
            post for post in self.posts.values() 
            if normalized_hashtag in post.hashtags
        ]
        
        # 可視性制限を適用
        if viewer_id:
            hashtag_posts = [
                post for post in hashtag_posts 
                if self._is_post_visible(post, viewer_id)
            ]
        else:
            # 閲覧者が指定されていない場合はパブリック投稿のみ
            hashtag_posts = [
                post for post in hashtag_posts 
                if post.visibility == PostVisibility.PUBLIC
            ]
        
        hashtag_posts.sort(key=lambda p: p.created_at, reverse=True)
        return hashtag_posts[:limit]
    
    # === フォロー機能 ===
    
    def follow_user(self, follower_id: str, following_id: str) -> bool:
        """ユーザーをフォロー"""
        # 基本的なバリデーション
        if not self.user_exists(follower_id) or not self.user_exists(following_id):
            return False
        
        if follower_id == following_id:
            return False  # 自分自身はフォローできない
        
        # ブロック関係チェック
        if self.is_blocked(follower_id, following_id) or self.is_blocked(following_id, follower_id):
            return False  # ブロック関係がある場合はフォローできない
        
        # 既にフォローしているかチェック
        if self.is_following(follower_id, following_id):
            return False
        
        # フォロー関係を作成
        follow = Follow(follower_id=follower_id, following_id=following_id)
        self.follows.append(follow)
        
        # フォロー通知を作成
        notification = Notification.create_follow_notification(
            user_id=following_id, 
            from_user_id=follower_id
        )
        self.notifications.append(notification)
        
        return True
    
    def unfollow_user(self, follower_id: str, following_id: str) -> bool:
        """ユーザーのフォローを解除"""
        for i, follow in enumerate(self.follows):
            if follow.follower_id == follower_id and follow.following_id == following_id:
                del self.follows[i]
                return True
        return False
    
    def is_following(self, follower_id: str, following_id: str) -> bool:
        """フォロー関係をチェック"""
        return any(
            follow.follower_id == follower_id and follow.following_id == following_id
            for follow in self.follows
        )
    
    def get_followers_list(self, user_id: str, limit: int = 100) -> List[str]:
        """フォロワーリストを取得"""
        followers = [
            follow.follower_id for follow in self.follows 
            if follow.following_id == user_id
        ]
        return followers[:limit]
    
    def get_following_list(self, user_id: str, limit: int = 100) -> List[str]:
        """フォロー中リストを取得"""
        following = [
            follow.following_id for follow in self.follows 
            if follow.follower_id == user_id
        ]
        return following[:limit]
    
    def get_followers_count(self, user_id: str) -> int:
        """フォロワー数を取得"""
        return len(self.get_followers_list(user_id))
    
    def get_following_count(self, user_id: str) -> int:
        """フォロー中数を取得"""
        return len(self.get_following_list(user_id))
    
    # === ブロック機能 ===
    
    def block_user(self, blocker_id: str, blocked_id: str) -> bool:
        """ユーザーをブロック"""
        # 基本的なバリデーション
        if not self.user_exists(blocker_id) or not self.user_exists(blocked_id):
            return False
        
        if blocker_id == blocked_id:
            return False  # 自分自身はブロックできない
        
        # 既にブロックしているかチェック
        if self.is_blocked(blocker_id, blocked_id):
            return False
        
        # ブロック関係を作成
        block = Block(blocker_id=blocker_id, blocked_id=blocked_id)
        self.blocks.append(block)
        
        # ブロックした相手をフォローしている場合は自動的にアンフォロー
        if self.is_following(blocker_id, blocked_id):
            self.unfollow_user(blocker_id, blocked_id)
        
        # ブロックした相手からフォローされている場合も自動的にアンフォロー
        if self.is_following(blocked_id, blocker_id):
            self.unfollow_user(blocked_id, blocker_id)
        
        return True
    
    def unblock_user(self, blocker_id: str, blocked_id: str) -> bool:
        """ユーザーのブロックを解除"""
        for i, block in enumerate(self.blocks):
            if block.blocker_id == blocker_id and block.blocked_id == blocked_id:
                del self.blocks[i]
                return True
        return False
    
    def is_blocked(self, blocker_id: str, blocked_id: str) -> bool:
        """ブロック関係をチェック"""
        return any(
            block.blocker_id == blocker_id and block.blocked_id == blocked_id
            for block in self.blocks
        )
    
    def get_blocked_list(self, user_id: str, limit: int = 100) -> List[str]:
        """ブロックしているユーザーリストを取得"""
        blocked = [
            block.blocked_id for block in self.blocks 
            if block.blocker_id == user_id
        ]
        return blocked[:limit]
    
    def get_blocked_by_list(self, user_id: str, limit: int = 100) -> List[str]:
        """このユーザーをブロックしているユーザーリストを取得"""
        blocked_by = [
            block.blocker_id for block in self.blocks 
            if block.blocked_id == user_id
        ]
        return blocked_by[:limit]
    
    def get_blocked_count(self, user_id: str) -> int:
        """ブロックしているユーザー数を取得"""
        return len(self.get_blocked_list(user_id))
    
    def _is_content_accessible(self, viewer_id: str, author_id: str) -> bool:
        """コンテンツへのアクセス権限をチェック（ブロック関係のみ）"""
        # 自分のコンテンツは常にアクセス可能
        if viewer_id == author_id:
            return True
        
        # 投稿者が閲覧者をブロックしている場合はアクセス不可
        if self.is_blocked(author_id, viewer_id):
            return False
        
        # 閲覧者が投稿者をブロックしている場合はアクセス不可
        if self.is_blocked(viewer_id, author_id):
            return False
        
        return True
    
    def _is_post_visible(self, post: Post, viewer_id: str) -> bool:
        """投稿の可視性をチェック（ブロック + プライバシー設定）"""
        # ブロック関係のチェック
        if not self._is_content_accessible(viewer_id, post.user_id):
            return False
        
        # 自分の投稿は常に閲覧可能
        if viewer_id == post.user_id:
            return True
        
        # 可視性設定によるチェック
        if post.visibility == PostVisibility.PUBLIC:
            return True
        
        elif post.visibility == PostVisibility.PRIVATE:
            return False  # 本人以外は閲覧不可
        
        elif post.visibility == PostVisibility.FOLLOWERS_ONLY:
            # フォロワーのみ閲覧可能
            return self.is_following(viewer_id, post.user_id)
        
        elif post.visibility == PostVisibility.MUTUAL_FOLLOWS_ONLY:
            # 相互フォローのみ閲覧可能
            return (self.is_following(viewer_id, post.user_id) and 
                    self.is_following(post.user_id, viewer_id))
        
        elif post.visibility == PostVisibility.SPECIFIED_USERS:
            # 指定ユーザーのみ閲覧可能
            return viewer_id in post.allowed_users
        
        return False
    
    # === いいね機能 ===
    
    def like_post(self, user_id: str, post_id: str) -> bool:
        """投稿にいいね"""
        post = self.get_post(post_id)
        if not self.user_exists(user_id) or not post:
            return False
        
        # 投稿可視性チェック
        if not self._is_post_visible(post, user_id):
            return False
        
        # 既にいいねしているかチェック
        if self.has_liked(user_id, post_id):
            return False
        
        # いいねを作成
        like = Like.create(user_id=user_id, post_id=post_id)
        self.likes.append(like)
        
        # いいね通知を作成（自分の投稿以外）
        if post.user_id != user_id:
            notification = Notification.create_like_notification(
                user_id=post.user_id,
                from_user_id=user_id,
                post_id=post_id
            )
            self.notifications.append(notification)
        
        return True
    
    def unlike_post(self, user_id: str, post_id: str) -> bool:
        """いいねを解除"""
        for i, like in enumerate(self.likes):
            if like.user_id == user_id and like.post_id == post_id:
                del self.likes[i]
                return True
        return False
    
    def has_liked(self, user_id: str, post_id: str) -> bool:
        """いいね済みかチェック"""
        return any(
            like.user_id == user_id and like.post_id == post_id
            for like in self.likes
        )
    
    def get_post_likes_count(self, post_id: str) -> int:
        """投稿のいいね数を取得"""
        return len([like for like in self.likes if like.post_id == post_id])
    
    # === 返信機能 ===
    
    def reply_to_post(self, user_id: str, post_id: str, content: str) -> Optional[Reply]:
        """投稿に返信"""
        post = self.get_post(post_id)
        if not self.user_exists(user_id) or not post:
            return None
        
        # 投稿可視性チェック
        if not self._is_post_visible(post, user_id):
            return None
        
        # 空の内容チェック
        if not content.strip():
            return None
        
        # 返信を作成
        reply = Reply.create(user_id=user_id, post_id=post_id, content=content)
        self.replies.append(reply)
        
        # 返信通知を作成（自分の投稿以外）
        if post.user_id != user_id:
            notification = Notification.create_reply_notification(
                user_id=post.user_id,
                from_user_id=user_id,
                post_id=post_id,
                reply_content=content
            )
            self.notifications.append(notification)
        
        # メンション処理
        self._process_mentions_in_content(content, user_id, post_id, reply.reply_id)
        
        return reply
    
    def get_post_replies(self, post_id: str, limit: int = 50) -> List[Reply]:
        """投稿の返信を取得"""
        post_replies = [reply for reply in self.replies if reply.post_id == post_id]
        post_replies.sort(key=lambda r: r.created_at)
        return post_replies[:limit]
    
    def get_post_replies_count(self, post_id: str) -> int:
        """投稿の返信数を取得"""
        return len([reply for reply in self.replies if reply.post_id == post_id])
    
    # === 通知機能 ===
    
    def get_user_notifications(self, user_id: str, unread_only: bool = False, limit: int = 50) -> List[Notification]:
        """ユーザーの通知を取得"""
        user_notifications = [
            notification for notification in self.notifications 
            if notification.user_id == user_id
        ]
        
        if unread_only:
            user_notifications = [n for n in user_notifications if not n.is_read]
        
        user_notifications.sort(key=lambda n: n.created_at, reverse=True)
        return user_notifications[:limit]
    
    def mark_notification_as_read(self, notification_id: str) -> bool:
        """通知を既読にマーク"""
        for i, notification in enumerate(self.notifications):
            if notification.notification_id == notification_id:
                self.notifications[i] = notification.mark_as_read()
                return True
        return False
    
    def get_unread_notifications_count(self, user_id: str) -> int:
        """未読通知数を取得"""
        return len(self.get_user_notifications(user_id, unread_only=True))
    
    # === 統計・情報取得 ===
    
    def get_system_stats(self) -> Dict[str, Any]:
        """システム全体の統計情報を取得"""
        # 可視性別の投稿数を計算
        visibility_counts = {}
        for post in self.posts.values():
            visibility = post.visibility.value
            visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1
        
        return {
            "total_users": len(self.users),
            "total_posts": len(self.posts),
            "total_follows": len(self.follows),
            "total_likes": len(self.likes),
            "total_replies": len(self.replies),
            "total_notifications": len(self.notifications),
            "total_blocks": len(self.blocks),
            "total_mentions": len(self.mentions),
            "posts_by_visibility": visibility_counts,
        } 
    
    # === メンション機能 ===
    
    def _process_mentions_in_content(self, content: str, user_id: str, post_id: str, reply_id: Optional[str] = None) -> List[str]:
        """コンテンツ内のメンションを処理し、通知を送信
        - トークンは user_id または users.name を許容
        - name が重複する場合は一致した全ユーザーにメンション（後方互換のための暫定仕様）
        """
        tokens = self._extract_mentions_from_content(content)
        unique_tokens = list(set(tokens))

        processed_mentions: List[str] = []
        for token in unique_tokens:
            resolved_user_ids = self._resolve_mention_token_to_user_ids(token)
            for mentioned_user_id in resolved_user_ids:
                if mentioned_user_id == user_id:
                    continue  # 自分自身はスキップ
                # ブロック関係をチェック
                if self.is_blocked(user_id, mentioned_user_id):
                    continue
                # メンションレコードを作成
                mention = Mention.create(
                    user_id=user_id,
                    mentioned_user_id=mentioned_user_id,
                    post_id=post_id,
                    reply_id=reply_id
                )
                self.mentions.append(mention)

                # メンション通知を作成
                notification = Notification.create_mention_notification(
                    user_id=mentioned_user_id,
                    from_user_id=user_id,
                    post_id=post_id,
                    reply_id=reply_id
                )
                self.notifications.append(notification)
                processed_mentions.append(mentioned_user_id)

        return processed_mentions

    def _resolve_mention_token_to_user_ids(self, token: str) -> List[str]:
        """メンショントークン(@の後ろ)をユーザーIDに解決する
        優先順位:
          1) user_id が一致
          2) users.name が一致（複数可。現状は全員を対象にする）
        将来的には users.handle (UNIQUE) を導入し、1) id, 2) handle, 3) name(非推奨) の順に解決する想定。
        """
        # user_id として存在する場合
        if self.user_exists(token):
            return [token]

        # name で検索（DBを優先。無ければメモリ）
        user_ids: List[str] = []
        try:
            self.cursor.execute(
                """
                SELECT user_id FROM users WHERE name = ?
                """,
                (token,)
            )
            rows = self.cursor.fetchall()
            user_ids = [row[0] for row in rows]
        except Exception:
            # フォールバック（メモリ保持の場合）
            if hasattr(self, "users") and isinstance(getattr(self, "users"), dict):
                user_ids = [uid for uid, u in self.users.items() if getattr(u, "name", None) == token]

        return user_ids

    def _find_user_by_name(self, name: str) -> Optional[str]:
        """ユーザー名からユーザーIDを検索"""
        for user_id, user in self.users.items():
            if user.name == name:
                return user_id
        return None
    
    def get_mentions_for_user(self, user_id: str) -> List[Mention]:
        """ユーザーがメンションされた記録を取得"""
        return [mention for mention in self.mentions if mention.mentioned_user_id == user_id]
    
    def get_mentions_by_user(self, user_id: str) -> List[Mention]:
        """ユーザーが行ったメンションを取得"""
        return [mention for mention in self.mentions if mention.user_id == user_id]
    
    def get_mentions_for_post(self, post_id: str) -> List[Mention]:
        """特定の投稿に含まれるメンションを取得"""
        return [mention for mention in self.mentions if mention.post_id == post_id] 