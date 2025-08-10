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
                    CHECK (visibility IN ('public', 'followers_only', 'mutual_follows_only', 'specified_users', 'private'))
                );
                CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at);
                CREATE INDEX IF NOT EXISTS idx_posts_user_created_at ON posts(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_posts_public_created_at ON posts(created_at) WHERE visibility = 'public';

                CREATE TABLE IF NOT EXISTS post_hashtags (
                    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                    hashtag TEXT NOT NULL,
                    PRIMARY KEY (post_id, hashtag)
                );                
                CREATE INDEX IF NOT EXISTS idx_post_hashtags_hashtag ON post_hashtags(hashtag);

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
                CREATE INDEX IF NOT EXISTS idx_follows_following_id ON follows(following_id);
                CREATE INDEX IF NOT EXISTS idx_follows_follower_id ON follows(follower_id);

                CREATE TABLE IF NOT EXISTS blocks (
                    blocker_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    blocked_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (blocker_id, blocked_id)
                );
                CREATE INDEX IF NOT EXISTS idx_blocks_blocked_id ON blocks(blocked_id);

                CREATE TABLE IF NOT EXISTS likes (
                    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (post_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_likes_user_id ON likes(user_id);
                CREATE INDEX IF NOT EXISTS idx_likes_post_id ON likes(post_id);

                CREATE TABLE IF NOT EXISTS mentions (
                    mention_id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
                    mentioner_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    mentioned_user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_mentions_mentioned_user_id ON mentions(mentioned_user_id);

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
        logger.debug("create_user: user_id=%s name=%s", user_id, name)
        now = int(time.time())
        self.cursor.execute(
            """
            INSERT INTO users (user_id, name, bio, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, name, bio, now)
        )
        self.db_conn.commit()
        logger.info("create_user: success user_id=%s", user_id)
        return SnsUser(user_id=user_id, name=name, bio=bio, created_at=now)
    
    def get_user(self, user_id: str) -> Optional[SnsUser]:
        """ユーザーを取得"""
        logger.debug("get_user: user_id=%s", user_id)
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
            logger.debug("get_user: found user_id=%s", user_id)
            return SnsUser(user_id=row[0], name=row[1], bio=row[2], created_at=row[3])
        logger.debug("get_user: not found user_id=%s", user_id)
        return None
    
    def update_user_bio(self, user_id: str, new_bio: str) -> Optional[SnsUser]:
        """ユーザーの一言コメントを更新"""
        logger.debug("update_user_bio: user_id=%s", user_id)
        self.cursor.execute(
            """
            UPDATE users
            SET bio = ?
            WHERE user_id = ?
            """,
            (new_bio, user_id)
        )
        self.db_conn.commit()
        logger.info("update_user_bio: success user_id=%s", user_id)
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
        exists = bool(self.cursor.fetchone()[0])
        logger.debug("user_exists: user_id=%s exists=%s", user_id, exists)
        return exists
    
    # === ユーティリティ ===
    def _extract_hashtags_from_content(self, content: str) -> List[str]:
        """投稿内容からハッシュタグを抽出"""
        import re
        hashtag_pattern = r'#[a-zA-Z0-9_@\-\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]+'
        tags = re.findall(hashtag_pattern, content)
        logger.debug("_extract_hashtags_from_content: count=%d", len(tags))
        return tags

    def _extract_mentions_from_content(self, content: str) -> List[str]:
        """投稿/返信内容からメンション（@ユーザー名）を抽出"""
        import re
        mention_pattern = r'@(\w+)'
        mentions = re.findall(mention_pattern, content)
        logger.debug("_extract_mentions_from_content: count=%d", len(mentions))
        return mentions

    def _resolve_mention_token_to_user_ids(self, tokens: List[str]) -> Dict[str, List[str]]:
        """複数のメンショントークン(@の後ろ)を一括でユーザーIDに解決する

        優先順位:
        1) token が `user_id` と一致する場合はその `user_id` を返す
        2) それ以外は `name` が token と一致するユーザーを全件返す（重名対応）

        Args:
            tokens: メンショントークンのリスト

        Returns:
            token をキー、解決された user_id のリストを値とする辞書。
            該当なしの場合は空リスト。
        """
        if not tokens:
            logger.debug("_resolve_mention_token_to_user_ids: no tokens")
            return {}

        unique_tokens: Set[str] = set(tokens)
        result: Dict[str, List[str]] = {token: [] for token in unique_tokens}

        try:
            placeholders = ",".join(["?"] * len(unique_tokens))
            self.cursor.execute(
                f"SELECT user_id FROM users WHERE user_id IN ({placeholders})",
                tuple(unique_tokens),
            )
            direct_rows = self.cursor.fetchall()
        except Exception:
            direct_rows = []

        matched_id_tokens: Set[str] = set()
        for row in direct_rows:
            user_id = row[0]
            result[user_id] = [user_id]
            matched_id_tokens.add(user_id)

        name_tokens = list(unique_tokens - matched_id_tokens)
        if name_tokens:
            try:
                name_placeholders = ",".join(["?"] * len(name_tokens))
                self.cursor.execute(
                    f"SELECT name, user_id FROM users WHERE name IN ({name_placeholders})",
                    tuple(name_tokens),
                )
                name_rows = self.cursor.fetchall()
            except Exception:
                name_rows = []

            for row in name_rows:
                name, user_id = row[0], row[1]
                result.setdefault(name, [])
                result[name].append(user_id)

        logger.debug("_resolve_mention_token_to_user_ids: tokens=%d resolved_tokens=%d", len(unique_tokens), len([k for k,v in result.items() if v]))
        return result
    
    # === 投稿機能 ===
    def create_post(self, user_id: str, content: str, hashtags: Optional[List[str]] = None, 
                   visibility: PostVisibility = PostVisibility.PUBLIC, 
                   allowed_users: Optional[List[str]] = None) -> Optional[Post]:
        """新しい投稿を作成（DB版）"""
        logger.debug("create_post: user_id=%s visibility=%s", user_id, visibility.value if hasattr(visibility, 'value') else visibility)
        if not self.user_exists(user_id):
            logger.warning("create_post: user not found: %s", user_id)
            return None

        # 指定ユーザー限定の検証
        valid_allowed_users: List[str] = []
        if visibility == PostVisibility.SPECIFIED_USERS:
            if not allowed_users:
                logger.warning("create_post: SPECIFIED_USERS requires allowed_users")
                return None
            valid_allowed_users = [uid for uid in allowed_users if self.user_exists(uid)]
            if not valid_allowed_users:
                logger.warning("create_post: no valid allowed_users for SPECIFIED_USERS")
                return None

        now = int(time.time())
        post_id = str(uuid.uuid4())

        # ハッシュタグ統合（引数 + 自動抽出）
        extracted_hashtags = self._extract_hashtags_from_content(content)
        all_hashtags_set = set(hashtags or []) | set(extracted_hashtags or [])
        all_hashtags: List[str] = list(all_hashtags_set)
            
        # メンション解決（@token -> user_ids）
        extracted_mentions = self._extract_mentions_from_content(content)
        token_to_user_ids = self._resolve_mention_token_to_user_ids(extracted_mentions) if extracted_mentions else {}
        mentioned_user_ids_set = set(uid for ids in token_to_user_ids.values() for uid in ids)
        logger.debug("create_post: hashtags=%d mentions=%d", len(all_hashtags), len(mentioned_user_ids_set))

        try:
            with self.db.transaction("IMMEDIATE"):
                # 投稿を作成（visibility は TEXT 値）
                self.cursor.execute(
                    """
                    INSERT INTO posts (post_id, user_id, content, visibility, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (post_id, user_id, content, visibility.value, now, now)
                )

                # ハッシュタグを一括挿入
                if all_hashtags:
                    self.cursor.executemany(
                        """
                        INSERT INTO post_hashtags (post_id, hashtag)
                        VALUES (?, ?)
                        """,
                        [(post_id, tag) for tag in all_hashtags]
                    )

                # 指定ユーザー限定の場合の許可ユーザー
                if visibility == PostVisibility.SPECIFIED_USERS and valid_allowed_users:
                    self.cursor.executemany(
                        """
                        INSERT INTO post_allowed_users (post_id, allowed_user_id)
                        VALUES (?, ?)
                        """,
                        [(post_id, uid) for uid in valid_allowed_users]
                    )

                # メンションと通知を一括挿入
                if mentioned_user_ids_set:
                    mention_rows = [
                        (str(uuid.uuid4()), post_id, user_id, mentioned_user_id, now)
                        for mentioned_user_id in mentioned_user_ids_set
                    ]
                    self.cursor.executemany(
                        """
                        INSERT INTO mentions (mention_id, post_id, mentioner_user_id, mentioned_user_id, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        mention_rows
                    )

                    notification_rows = [
                        (str(uuid.uuid4()), mentioned_user_id, user_id, post_id, NotificationType.MENTION.value, 0, now)
                        for mentioned_user_id in mentioned_user_ids_set
                    ]
                    self.cursor.executemany(
                        """
                        INSERT INTO notifications (notification_id, user_id, actor_id, post_id, notification_type, is_read, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        notification_rows
                    )

            logger.info(
                "create_post: success post_id=%s user_id=%s hashtags=%d mentions=%d visibility=%s",
                post_id, user_id, len(all_hashtags), len(mentioned_user_ids_set), visibility.value
            )
            # 戻り値のPostはデータモデルに合わせて構築
            return Post(
                post_id=post_id,
                user_id=user_id,
                content=content,
                hashtags=all_hashtags,
                visibility=visibility,
                allowed_users=valid_allowed_users,
                created_at=datetime.fromtimestamp(now),
                updated_at=datetime.fromtimestamp(now),
            )
        except Exception as e:
            logger.exception("create_post: failed post_id=%s user_id=%s: %s", post_id, user_id, e)
            return None
    
    def get_post(self, post_id: str) -> Optional[Post]:
        """投稿を取得"""
        logger.debug("get_post: post_id=%s", post_id)
        self.cursor.execute(
            """
            SELECT post_id, user_id, content, visibility, created_at, updated_at
            FROM posts
            WHERE post_id = ?
            """,
            (post_id,)
        )
        row = self.cursor.fetchone()
        if row:
            logger.debug("get_post: found post_id=%s", post_id)
            return Post(
                post_id=row[0],
                user_id=row[1],
                content=row[2],
                visibility=PostVisibility(row[3]),
                created_at=datetime.fromtimestamp(row[4]),
                updated_at=datetime.fromtimestamp(row[5]),
            )
        logger.debug("get_post: not found post_id=%s", post_id)
        return None
    
    def get_user_posts(self, user_id: str, limit: int = 20) -> List[Post]:
        """特定のユーザーの投稿を取得"""
        logger.debug("get_user_posts: user_id=%s limit=%d", user_id, limit)
        self.cursor.execute(
            """
            SELECT post_id, user_id, content, visibility, created_at, updated_at
            FROM posts
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit)
        )
        rows = self.cursor.fetchall()
        logger.debug("get_user_posts: user_id=%s fetched=%d", user_id, len(rows))
        return [
            Post(
            post_id=row[0],
            user_id=row[1],
            content=row[2],
            visibility=PostVisibility(row[3]),
            created_at=datetime.fromtimestamp(row[4]),
            updated_at=datetime.fromtimestamp(row[5]),  
        ) for row in rows]
    
    # === タイムライン機能 ===
    def get_user_posts_before(self, user_id: str, limit: int, created_at: int) -> List[Post]:
        """指定ユーザーの、created_at(UNIX秒)以前の投稿を新しい順で最大limit件取得

        初回は現在時刻を渡し、取得結果の最古の created_at を次回のカーソルに使う想定。
        """
        logger.debug("get_user_posts_before: user_id=%s limit=%d created_at=%d", user_id, limit, created_at)
        if not self.user_exists(user_id):
            return []

        # 投稿本体を取得（visibilityはTEXTで保存されている）
        self.cursor.execute(
            """
            SELECT post_id, user_id, content, visibility, created_at, updated_at
            FROM posts
            WHERE user_id = ? AND created_at <= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, created_at, limit),
        )
        rows = self.cursor.fetchall()
        if not rows:
            logger.debug("get_user_posts_before: no rows user_id=%s", user_id)
            return []

        post_ids = [row[0] for row in rows]

        # ハッシュタグをまとめて取得
        hashtags_map: Dict[str, List[str]] = {pid: [] for pid in post_ids}
        placeholders = ",".join(["?"] * len(post_ids))
        self.cursor.execute(
            f"SELECT post_id, hashtag FROM post_hashtags WHERE post_id IN ({placeholders})",
            tuple(post_ids),
        )
        for hrow in self.cursor.fetchall():
            pid, tag = hrow[0], hrow[1]
            hashtags_map.setdefault(pid, []).append(tag)

        # 指定ユーザー限定の許可ユーザーをまとめて取得
        allowed_map: Dict[str, List[str]] = {pid: [] for pid in post_ids}
        self.cursor.execute(
            f"SELECT post_id, allowed_user_id FROM post_allowed_users WHERE post_id IN ({placeholders})",
            tuple(post_ids),
        )
        for arow in self.cursor.fetchall():
            pid, allowed_uid = arow[0], arow[1]
            allowed_map.setdefault(pid, []).append(allowed_uid)

        # Post オブジェクトへ変換
        results: List[Post] = []
        for row in rows:
            pid, uid, content, visibility_text, c_at, u_at = row
            try:
                visibility_enum = PostVisibility(visibility_text)
            except Exception:
                visibility_enum = PostVisibility.PUBLIC
            results.append(
                Post(
                    post_id=pid,
                    user_id=uid,
                    content=content,
                    hashtags=hashtags_map.get(pid, []),
                    visibility=visibility_enum,
                    allowed_users=allowed_map.get(pid, []),
                    created_at=datetime.fromtimestamp(c_at),
                    updated_at=datetime.fromtimestamp(u_at),
                )
            )

        logger.debug("get_user_posts_before: user_id=%s returned=%d", user_id, len(results))
        return results
    
    def get_global_timeline_before(self, *, viewer_id: Optional[str], limit: int, created_at: int) -> List[Post]:
        """グローバルタイムライン（created_at 以前の最新投稿を新しい順に limit 件）

        - viewer_id が None の場合: パブリック投稿のみ
        - viewer_id が指定される場合: 可視性制限（ブロック/フォロー/相互/指定ユーザー/本人）を適用
        """
        logger.debug("get_global_timeline_before: viewer_id=%s limit=%d created_at=%d", viewer_id, limit, created_at)
        if limit <= 0:
            return []

        if viewer_id is None:
            # 公開投稿のみ
            self.cursor.execute(
                """
                SELECT post_id, user_id, content, visibility, created_at, updated_at
                FROM posts
                WHERE visibility = 'public' AND created_at <= ?  -- 公開投稿 & 作成日時がcreated_atより過去の投稿
                ORDER BY created_at DESC  -- 新しい順に並べ替え
                LIMIT ?
                """,
                (created_at, limit),
            )
            rows = self.cursor.fetchall()
        else:
            # CTE + UNION で簡潔化
            sql = """
                WITH accessible AS (
                    SELECT p.*
                    FROM posts p
                    WHERE p.created_at <= ?  -- 作成日時がcreated_atより過去の投稿
                      AND (
                        p.user_id = ? OR (  -- 本人の投稿
                            NOT EXISTS (SELECT 1 FROM blocks b WHERE b.blocker_id = p.user_id AND b.blocked_id = ?)  -- ポストの投稿者にブロックされていないことをチェック
                            AND NOT EXISTS (SELECT 1 FROM blocks b2 WHERE b2.blocker_id = ? AND b2.blocked_id = p.user_id)  -- 自分がポストの投稿者をブロックしていないことをチェック
                        )
                      )
                ),  -- 本人の投稿、でありブロック関係がない投稿を取得
                filtered AS (  -- UNIONを使って、4つのSELECTの結果を結合
                    SELECT * FROM accessible WHERE visibility = 'public'  -- 公開投稿
                    UNION
                    SELECT * FROM accessible a
                      WHERE a.visibility = 'followers_only'  -- ポストの可視性がフォロワー限定のものを抽出
                        AND EXISTS (
                          SELECT 1 FROM follows f
                          WHERE f.follower_id = ? AND f.following_id = a.user_id
                        )  -- ポストの投稿者(a.user_id)が自分をフォローしていることをチェック
                    UNION
                    SELECT * FROM accessible a
                      WHERE a.visibility = 'mutual_follows_only'  -- ポストの可視性が相互フォロー限定のものを抽出
                        AND EXISTS (
                          SELECT 1 FROM follows f1
                          WHERE f1.follower_id = ? AND f1.following_id = a.user_id
                        )  -- ポストの投稿者(a.user_id)が自分をフォローしていることをチェック
                        AND EXISTS (
                          SELECT 1 FROM follows f2
                          WHERE f2.follower_id = a.user_id AND f2.following_id = ?
                        )  -- 自分がポストの投稿者(a.user_id)をフォローしていることをチェック
                    UNION
                    SELECT * FROM accessible a
                      WHERE a.visibility = 'specified_users'  -- ポストの可視性が指定ユーザー限定のものを抽出
                        AND (a.user_id = ? OR EXISTS (  -- ポストの投稿者(a.user_id)が自分か、ポストの許可ユーザー(au.allowed_user_id)に自分が含まれていることをチェック
                              SELECT 1 FROM post_allowed_users au
                              WHERE au.post_id = a.post_id AND au.allowed_user_id = ?
                            ))
                )
                SELECT post_id, user_id, content, visibility, created_at, updated_at
                FROM filtered
                ORDER BY created_at DESC
                LIMIT ?
            """
            params = (
                created_at,
                viewer_id,  # accessible: self
                viewer_id,  # accessible: block check 1
                viewer_id,  # accessible: block check 2
                viewer_id,  # followers_only
                viewer_id,  # mutual forward
                viewer_id,  # mutual reverse
                viewer_id,  # specified self
                viewer_id,  # specified allowed
                limit,
            )
            self.cursor.execute(sql, params)
            rows = self.cursor.fetchall()

        if not rows:
            logger.debug("get_global_timeline_before: no rows viewer_id=%s", viewer_id)
            return []

        post_ids = [row[0] for row in rows]

        # postに付随する情報を取得
        # ハッシュタグをまとめて取得
        hashtags_map: Dict[str, List[str]] = {pid: [] for pid in post_ids}
        placeholders = ",".join(["?"] * len(post_ids))
        self.cursor.execute(
            f"SELECT post_id, hashtag FROM post_hashtags WHERE post_id IN ({placeholders})",
            tuple(post_ids),
        )
        for hrow in self.cursor.fetchall():
            pid, tag = hrow[0], hrow[1]
            hashtags_map.setdefault(pid, []).append(tag)

        # 指定ユーザー限定の許可ユーザーをまとめて取得
        allowed_map: Dict[str, List[str]] = {pid: [] for pid in post_ids}
        self.cursor.execute(
            f"SELECT post_id, allowed_user_id FROM post_allowed_users WHERE post_id IN ({placeholders})",
            tuple(post_ids),
        )
        for arow in self.cursor.fetchall():
            pid, allowed_uid = arow[0], arow[1]
            allowed_map.setdefault(pid, []).append(allowed_uid)

        results: List[Post] = []
        for row in rows:
            pid, uid, content, visibility_text, c_at, u_at = row
            try:
                visibility_enum = PostVisibility(visibility_text)
            except Exception:
                visibility_enum = PostVisibility.PUBLIC
            results.append(
                Post(
                    post_id=pid,
                    user_id=uid,
            content=content, 
                    hashtags=hashtags_map.get(pid, []),
                    visibility=visibility_enum,
                    allowed_users=allowed_map.get(pid, []),
                    created_at=datetime.fromtimestamp(c_at),
                    updated_at=datetime.fromtimestamp(u_at),
                )
            )

        logger.debug("get_global_timeline_before: viewer_id=%s returned=%d", viewer_id, len(results))
        return results
    
    def get_following_timeline_before(self, user_id: str, limit: int, created_at: int) -> List[Post]:
        """フォロー中のユーザーのタイムラインを取得（created_at 以前の新しい順で limit 件）"""
        logger.debug("get_following_timeline_before: user_id=%s limit=%d created_at=%d", user_id, limit, created_at)
        if limit <= 0:
            return []

        sql = """
        WITH accessible AS (
            SELECT p.*
            FROM posts p
            WHERE p.created_at <= ?  -- 作成日時がcreated_atより過去の投稿
              AND p.user_id <> ?     -- 本人の投稿を除外
              AND (
                NOT EXISTS (
                  SELECT 1 FROM blocks b
                  WHERE b.blocker_id = p.user_id AND b.blocked_id = ?
                ) -- 投稿者にブロックされていない
                AND NOT EXISTS (
                  SELECT 1 FROM blocks b2
                  WHERE b2.blocker_id = ? AND b2.blocked_id = p.user_id
                ) -- 自分が投稿者をブロックしていない
              )
        ),
        filtered AS (
            -- 公開投稿: 自分が投稿者をフォローしている
            SELECT * FROM accessible a
            WHERE a.visibility = 'public'
              AND EXISTS (
                SELECT 1 FROM follows f
                WHERE f.follower_id = ? AND f.following_id = a.user_id
              )
            UNION
            -- フォロワー限定: 自分が投稿者をフォローしている
            SELECT * FROM accessible a
            WHERE a.visibility = 'followers_only'
              AND EXISTS (
                SELECT 1 FROM follows f
                WHERE f.follower_id = ? AND f.following_id = a.user_id
              )
            UNION
            -- 相互フォロー限定: 双方向のフォローが成立
            SELECT * FROM accessible a
            WHERE a.visibility = 'mutual_follows_only'
              AND EXISTS (
                SELECT 1 FROM follows f1
                WHERE f1.follower_id = ? AND f1.following_id = a.user_id
              )
              AND EXISTS (
                SELECT 1 FROM follows f2
                WHERE f2.follower_id = a.user_id AND f2.following_id = ?
              )
            UNION
            -- 指定ユーザー限定: 自分が投稿者をフォロー AND 自分が許可ユーザー
            SELECT * FROM accessible a
            WHERE a.visibility = 'specified_users'
              AND EXISTS (
                SELECT 1 FROM follows f
                WHERE f.follower_id = ? AND f.following_id = a.user_id
              )
              AND EXISTS (
                SELECT 1 FROM post_allowed_users au
                WHERE au.post_id = a.post_id AND au.allowed_user_id = ?
              )
        )
        SELECT post_id, user_id, content, visibility, created_at, updated_at
        FROM filtered
        ORDER BY created_at DESC
        LIMIT ?
        """

        params = (
            created_at,
            user_id,
            user_id,
            user_id,
            user_id,  # public follow check
            user_id,  # followers_only follow check
            user_id,  # mutual forward
            user_id,  # mutual reverse
            user_id,  # specified follow check
            user_id,  # specified allowed check
            limit,
        )

        self.cursor.execute(sql, params)
        rows = self.cursor.fetchall()
        if not rows:
            logger.debug("get_following_timeline_before: no rows user_id=%s", user_id)
            return []

        post_ids = [row[0] for row in rows]

        # 付随情報の取得
        hashtags_map: Dict[str, List[str]] = {pid: [] for pid in post_ids}
        placeholders = ",".join(["?"] * len(post_ids))
        self.cursor.execute(
            f"SELECT post_id, hashtag FROM post_hashtags WHERE post_id IN ({placeholders})",
            tuple(post_ids),
        )
        for hrow in self.cursor.fetchall():
            pid, tag = hrow[0], hrow[1]
            hashtags_map.setdefault(pid, []).append(tag)

        allowed_map: Dict[str, List[str]] = {pid: [] for pid in post_ids}
        self.cursor.execute(
            f"SELECT post_id, allowed_user_id FROM post_allowed_users WHERE post_id IN ({placeholders})",
            tuple(post_ids),
        )
        for arow in self.cursor.fetchall():
            pid, allowed_uid = arow[0], arow[1]
            allowed_map.setdefault(pid, []).append(allowed_uid)

        results: List[Post] = []
        for row in rows:
            pid, uid, content, visibility_text, c_at, u_at = row
            try:
                visibility_enum = PostVisibility(visibility_text)
            except Exception:
                visibility_enum = PostVisibility.PUBLIC
            results.append(
                Post(
                    post_id=pid,
                    user_id=uid,
                    content=content,
                    hashtags=hashtags_map.get(pid, []),
                    visibility=visibility_enum,
                    allowed_users=allowed_map.get(pid, []),
                    created_at=datetime.fromtimestamp(c_at),
                    updated_at=datetime.fromtimestamp(u_at),
                )
            )

        logger.debug("get_following_timeline_before: user_id=%s returned=%d", user_id, len(results))
        return results
    
    def get_hashtag_timeline_before(self, hashtag: str, viewer_id: Optional[str], limit: int, created_at: int) -> List[Post]:
        """特定のハッシュタグのタイムラインを取得（created_at 以前の新しい順で limit 件）"""
        logger.debug("get_hashtag_timeline_before: hashtag=%s viewer_id=%s limit=%d created_at=%d", hashtag, viewer_id, limit, created_at)
        if limit <= 0:
            return []

        normalized_hashtag = hashtag if hashtag.startswith('#') else f'#{hashtag}'
        
        if viewer_id is None:
            # 公開投稿のみ
            self.cursor.execute(
                """
                SELECT p.post_id, p.user_id, p.content, p.visibility, p.created_at, p.updated_at
                FROM posts p
                INNER JOIN post_hashtags h ON h.post_id = p.post_id
                WHERE h.hashtag = ?
                  AND p.visibility = 'public'
                  AND p.created_at <= ?
                ORDER BY p.created_at DESC
                LIMIT ?
                """,
                (normalized_hashtag, created_at, limit),
            )
            rows = self.cursor.fetchall()
        else:
            # viewer の可視性制限を適用
            sql = """
                WITH accessible AS (
                    SELECT p.*
                    FROM posts p
                    WHERE p.created_at <= ?
                      AND EXISTS (
                        SELECT 1 FROM post_hashtags ph
                        WHERE ph.post_id = p.post_id AND ph.hashtag = ?
                      )
                      AND (
                        p.user_id = ? OR (
                          NOT EXISTS (SELECT 1 FROM blocks b WHERE b.blocker_id = p.user_id AND b.blocked_id = ?)
                          AND NOT EXISTS (SELECT 1 FROM blocks b2 WHERE b2.blocker_id = ? AND b2.blocked_id = p.user_id)
                        )
                      )
                ),
                filtered AS (
                    SELECT * FROM accessible WHERE visibility = 'public'
                    UNION
                    SELECT * FROM accessible a
                      WHERE a.visibility = 'followers_only'
                        AND EXISTS (
                          SELECT 1 FROM follows f
                          WHERE f.follower_id = ? AND f.following_id = a.user_id
                        )
                    UNION
                    SELECT * FROM accessible a
                      WHERE a.visibility = 'mutual_follows_only'
                        AND EXISTS (
                          SELECT 1 FROM follows f1
                          WHERE f1.follower_id = ? AND f1.following_id = a.user_id
                        )
                        AND EXISTS (
                          SELECT 1 FROM follows f2
                          WHERE f2.follower_id = a.user_id AND f2.following_id = ?
                        )
                    UNION
                    SELECT * FROM accessible a
                      WHERE a.visibility = 'specified_users'
                        AND (a.user_id = ? OR EXISTS (
                              SELECT 1 FROM post_allowed_users au
                              WHERE au.post_id = a.post_id AND au.allowed_user_id = ?
                            ))
                )
                SELECT post_id, user_id, content, visibility, created_at, updated_at
                FROM filtered
                ORDER BY created_at DESC
                LIMIT ?
            """
            params = (
                created_at,
                normalized_hashtag,
                viewer_id,  # accessible: self
                viewer_id,  # block check 1
                viewer_id,  # block check 2
                viewer_id,  # followers_only
                viewer_id,  # mutual forward
                viewer_id,  # mutual reverse
                viewer_id,  # specified self
                viewer_id,  # specified allowed
                limit,
            )
            self.cursor.execute(sql, params)
            rows = self.cursor.fetchall()

        if not rows:
            logger.debug("get_hashtag_timeline_before: no rows hashtag=%s viewer_id=%s", hashtag, viewer_id)
            return []

        post_ids = [row[0] for row in rows]

        # 付随情報
        hashtags_map: Dict[str, List[str]] = {pid: [] for pid in post_ids}
        placeholders = ",".join(["?"] * len(post_ids))
        self.cursor.execute(
            f"SELECT post_id, hashtag FROM post_hashtags WHERE post_id IN ({placeholders})",
            tuple(post_ids),
        )
        for hrow in self.cursor.fetchall():
            pid, tag = hrow[0], hrow[1]
            hashtags_map.setdefault(pid, []).append(tag)

        allowed_map: Dict[str, List[str]] = {pid: [] for pid in post_ids}
        self.cursor.execute(
            f"SELECT post_id, allowed_user_id FROM post_allowed_users WHERE post_id IN ({placeholders})",
            tuple(post_ids),
        )
        for arow in self.cursor.fetchall():
            pid, allowed_uid = arow[0], arow[1]
            allowed_map.setdefault(pid, []).append(allowed_uid)

        results: List[Post] = []
        for row in rows:
            pid, uid, content, visibility_text, c_at, u_at = row
            try:
                visibility_enum = PostVisibility(visibility_text)
            except Exception:
                visibility_enum = PostVisibility.PUBLIC
            results.append(
                Post(
                    post_id=pid,
                    user_id=uid,
                    content=content,
                    hashtags=hashtags_map.get(pid, []),
                    visibility=visibility_enum,
                    allowed_users=allowed_map.get(pid, []),
                    created_at=datetime.fromtimestamp(c_at),
                    updated_at=datetime.fromtimestamp(u_at),
                )
            )

        logger.debug("get_hashtag_timeline_before: hashtag=%s viewer_id=%s returned=%d", hashtag, viewer_id, len(results))
        return results
    
    # === フォロー機能 ===
    def follow_user(self, follower_id: str, following_id: str) -> bool:
        """ユーザーをフォロー"""
        logger.debug("follow_user: follower_id=%s following_id=%s", follower_id, following_id)
        # バリデーション
        if not self.user_exists(follower_id) or not self.user_exists(following_id):
            logger.debug("follow_user: user not exists")
            return False
        if follower_id == following_id:
            logger.debug("follow_user: cannot follow self")
            return False
        # ブロック関係
        self.cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?)",
            (follower_id, following_id),
        )
        if self.cursor.fetchone()[0]:
            logger.debug("follow_user: blocked by target")
            return False
        self.cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?)",
            (following_id, follower_id),
        )
        if self.cursor.fetchone()[0]:
            logger.debug("follow_user: you blocked target")
            return False

        # 既にフォローしているか
        if self.is_following(follower_id, following_id):
            logger.debug("follow_user: already following")
            return False
        
        now = int(time.time())
        with self.db.transaction("IMMEDIATE"):
            self.cursor.execute(
                "INSERT INTO follows (follower_id, following_id, created_at) VALUES (?, ?, ?)",
                (follower_id, following_id, now),
            )
            # 通知作成
            notification = Notification.create_follow_notification(
                user_id=following_id, from_user_id=follower_id
            )
            self.cursor.execute(
                """
                INSERT INTO notifications (notification_id, user_id, actor_id, post_id, notification_type, is_read, created_at)
                VALUES (?, ?, ?, NULL, ?, 0, ?)
                """,
                (
                    notification.notification_id,
                    notification.user_id,
                    notification.from_user_id,
                    notification.type.value,
                    int(notification.created_at.timestamp()),
                ),
            )
        logger.info("follow_user: success follower_id=%s following_id=%s", follower_id, following_id)
        return True
    
    def unfollow_user(self, follower_id: str, following_id: str) -> bool:
        """ユーザーのフォローを解除"""
        logger.debug("unfollow_user: follower_id=%s following_id=%s", follower_id, following_id)
        with self.db.transaction("IMMEDIATE"):
            cur = self.cursor.execute(
                "DELETE FROM follows WHERE follower_id=? AND following_id=?",
                (follower_id, following_id),
            )
            success = cur.rowcount > 0
            if success:
                logger.info("unfollow_user: success follower_id=%s following_id=%s", follower_id, following_id)
            else:
                logger.debug("unfollow_user: not following follower_id=%s following_id=%s", follower_id, following_id)
            return success
    
    def is_following(self, follower_id: str, following_id: str) -> bool:
        """フォロー関係をチェック"""
        self.cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM follows WHERE follower_id=? AND following_id=?)",
            (follower_id, following_id),
        )
        result = bool(self.cursor.fetchone()[0])
        logger.debug("is_following: %s -> %s = %s", follower_id, following_id, result)
        return result
    
    def get_followers_list(self, user_id: str, limit: int = 100) -> List[str]:
        """フォロワーリストを取得"""
        logger.debug("get_followers_list: user_id=%s limit=%d", user_id, limit)
        self.cursor.execute(
            "SELECT follower_id FROM follows WHERE following_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = [row[0] for row in self.cursor.fetchall()]
        logger.debug("get_followers_list: user_id=%s count=%d", user_id, len(rows))
        return rows
    
    def get_following_list(self, user_id: str, limit: int = 100) -> List[str]:
        """フォロー中リストを取得"""
        logger.debug("get_following_list: user_id=%s limit=%d", user_id, limit)
        self.cursor.execute(
            "SELECT following_id FROM follows WHERE follower_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = [row[0] for row in self.cursor.fetchall()]
        logger.debug("get_following_list: user_id=%s count=%d", user_id, len(rows))
        return rows
    
    def get_followers_count(self, user_id: str) -> int:
        """フォロワー数を取得"""
        self.cursor.execute(
            "SELECT COUNT(*) FROM follows WHERE following_id=?",
            (user_id,),
        )
        count = int(self.cursor.fetchone()[0])
        logger.debug("get_followers_count: user_id=%s count=%d", user_id, count)
        return count
    
    def get_following_count(self, user_id: str) -> int:
        """フォロー中数を取得"""
        self.cursor.execute(
            "SELECT COUNT(*) FROM follows WHERE follower_id=?",
            (user_id,),
        )
        count = int(self.cursor.fetchone()[0])
        logger.debug("get_following_count: user_id=%s count=%d", user_id, count)
        return count
    
    # === ブロック機能 ===
    
    def block_user(self, blocker_id: str, blocked_id: str) -> bool:
        """ユーザーをブロック（DB版）"""
        logger.debug("block_user: blocker_id=%s blocked_id=%s", blocker_id, blocked_id)
        if not self.user_exists(blocker_id) or not self.user_exists(blocked_id):
            return False
        if blocker_id == blocked_id:
            return False
        if self.is_blocked(blocker_id, blocked_id):
            return False
        
        now = int(time.time())
        with self.db.transaction("IMMEDIATE"):
            self.cursor.execute(
                "INSERT INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, ?)",
                (blocker_id, blocked_id, now),
            )
            # 双方向のフォローを整理
            self.cursor.execute(
                "DELETE FROM follows WHERE follower_id=? AND following_id=?",
                (blocker_id, blocked_id),
            )
            self.cursor.execute(
                "DELETE FROM follows WHERE follower_id=? AND following_id=?",
                (blocked_id, blocker_id),
            )
        logger.info("block_user: success blocker_id=%s blocked_id=%s", blocker_id, blocked_id)
        return True
    
    def unblock_user(self, blocker_id: str, blocked_id: str) -> bool:
        """ユーザーのブロックを解除（DB版）"""
        logger.debug("unblock_user: blocker_id=%s blocked_id=%s", blocker_id, blocked_id)
        with self.db.transaction("IMMEDIATE"):
            cur = self.cursor.execute(
                "DELETE FROM blocks WHERE blocker_id=? AND blocked_id=?",
                (blocker_id, blocked_id),
            )
            success = cur.rowcount > 0
            if success:
                logger.info("unblock_user: success blocker_id=%s blocked_id=%s", blocker_id, blocked_id)
            else:
                logger.debug("unblock_user: not blocked blocker_id=%s blocked_id=%s", blocker_id, blocked_id)
            return success
    
    def is_blocked(self, blocker_id: str, blocked_id: str) -> bool:
        """ブロック関係をチェック（DB版）"""
        self.cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?)",
            (blocker_id, blocked_id),
        )
        result = bool(self.cursor.fetchone()[0])
        logger.debug("is_blocked: %s -> %s = %s", blocker_id, blocked_id, result)
        return result
    
    def get_blocked_list(self, user_id: str, limit: int = 100) -> List[str]:
        """ブロックしているユーザーリストを取得"""
        self.cursor.execute(
            """
            SELECT blocked_id
            FROM blocks
            WHERE blocker_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = [row[0] for row in self.cursor.fetchall()]
        return rows
    
    def get_blocked_by_list(self, user_id: str, limit: int = 100) -> List[str]:
        """このユーザーをブロックしているユーザーリストを取得"""
        self.cursor.execute(
            """
            SELECT blocker_id
            FROM blocks
            WHERE blocked_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = [row[0] for row in self.cursor.fetchall()]
        return rows
    
    def get_blocked_count(self, user_id: str) -> int:
        """ブロックしているユーザー数を取得"""
        self.cursor.execute(
            "SELECT COUNT(*) FROM blocks WHERE blocker_id = ?",
            (user_id,),
        )
        return int(self.cursor.fetchone()[0])
    
    # === いいね機能 ===
    def like_post(self, user_id: str, post_id: str) -> bool:
        """投稿にいいね"""
        logger.debug("like_post: user_id=%s post_id=%s", user_id, post_id)
        post = self.get_post(post_id)
        if not self.user_exists(user_id) or not post:
            logger.debug("like_post: user or post not found")
            return False
        
        # 可視性チェック（DBロジックと同等）。自分の投稿は常に許可。
        if user_id != post.user_id:
            self.cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?)",
                (post.user_id, user_id),
            )
            if self.cursor.fetchone()[0]:
                logger.debug("like_post: blocked by author")
                return False
            self.cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?)",
                (user_id, post.user_id),
            )
            if self.cursor.fetchone()[0]:
                logger.debug("like_post: you blocked author")
                return False
        
            if post.visibility == PostVisibility.PRIVATE:
                logger.debug("like_post: private post")
                return False
            elif post.visibility == PostVisibility.FOLLOWERS_ONLY:
                if not self.is_following(user_id, post.user_id):
                    logger.debug("like_post: not follower")
                    return False
            elif post.visibility == PostVisibility.MUTUAL_FOLLOWS_ONLY:
                if not (self.is_following(user_id, post.user_id) and self.is_following(post.user_id, user_id)):
                    logger.debug("like_post: not mutual follows")
                    return False
            elif post.visibility == PostVisibility.SPECIFIED_USERS:
                self.cursor.execute(
                    "SELECT EXISTS(SELECT 1 FROM post_allowed_users WHERE post_id=? AND allowed_user_id=?)",
                    (post.post_id, user_id),
                )
                if not self.cursor.fetchone()[0]:
                    logger.debug("like_post: not in allowed users")
                    return False
    
        # 既にいいね済みか
        self.cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM likes WHERE post_id=? AND user_id=?)",
            (post_id, user_id),
        )
        if self.cursor.fetchone()[0]:
            logger.debug("like_post: already liked")
            return False
        
        now = int(time.time())
        with self.db.transaction("IMMEDIATE"):
            # いいね作成
            self.cursor.execute(
                "INSERT INTO likes (post_id, user_id, created_at) VALUES (?, ?, ?)",
                (post_id, user_id, now),
            )
            # 通知（自分の投稿以外）
            if post.user_id != user_id:
                notification = Notification.create_like_notification(
                    user_id=post.user_id, from_user_id=user_id, post_id=post_id
                )
                self.cursor.execute(
                    """
                    INSERT INTO notifications (notification_id, user_id, actor_id, post_id, notification_type, is_read, created_at)
                    VALUES (?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        notification.notification_id,
                        notification.user_id,
                        notification.from_user_id,
                        post_id,
                        notification.type.value,
                        int(notification.created_at.timestamp()),
                    ),
                )
        logger.info("like_post: success user_id=%s post_id=%s", user_id, post_id)
        return True
    
    def unlike_post(self, user_id: str, post_id: str) -> bool:
        """いいねを解除"""
        logger.debug("unlike_post: user_id=%s post_id=%s", user_id, post_id)
        with self.db.transaction("IMMEDIATE"):
            cur = self.cursor.execute(
                "DELETE FROM likes WHERE post_id=? AND user_id=?",
                (post_id, user_id),
            )
            success = cur.rowcount > 0
            if success:
                logger.info("unlike_post: success user_id=%s post_id=%s", user_id, post_id)
            else:
                logger.debug("unlike_post: not liked user_id=%s post_id=%s", user_id, post_id)
            return success
    
    def has_liked(self, user_id: str, post_id: str) -> bool:
        """いいね済みかチェック"""
        self.cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM likes WHERE post_id=? AND user_id=?)",
            (post_id, user_id),
        )
        result = bool(self.cursor.fetchone()[0])
        logger.debug("has_liked: user_id=%s post_id=%s = %s", user_id, post_id, result)
        return result
    
    def get_post_likes_count(self, post_id: str) -> int:
        """投稿のいいね数を取得"""
        self.cursor.execute(
            "SELECT COUNT(*) FROM likes WHERE post_id=?",
            (post_id,),
        )
        count = int(self.cursor.fetchone()[0])
        logger.debug("get_post_likes_count: post_id=%s count=%d", post_id, count)
        return count
    
    # === 返信機能 ===
    
    def reply_to_post(self, user_id: str, post_id: str, content: str) -> Optional[Reply]:
        """投稿に返信（DB版）"""
        logger.debug("reply_to_post: user_id=%s post_id=%s", user_id, post_id)
        original = self.get_post(post_id)
        if not self.user_exists(user_id) or not original:
            logger.debug("reply_to_post: user or original post not found")
            return None

        # 可視性チェック（like_post と同様）
        if user_id != original.user_id:
            self.cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?)",
                (original.user_id, user_id),
            )
            if self.cursor.fetchone()[0]:
                return None
            self.cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?)",
                (user_id, original.user_id),
            )
            if self.cursor.fetchone()[0]:
                return None

            if original.visibility == PostVisibility.PRIVATE:
                return None
            elif original.visibility == PostVisibility.FOLLOWERS_ONLY:
                if not self.is_following(user_id, original.user_id):
                    return None
            elif original.visibility == PostVisibility.MUTUAL_FOLLOWS_ONLY:
                if not (self.is_following(user_id, original.user_id) and self.is_following(original.user_id, user_id)):
                    return None
            elif original.visibility == PostVisibility.SPECIFIED_USERS:
                self.cursor.execute(
                    "SELECT EXISTS(SELECT 1 FROM post_allowed_users WHERE post_id=? AND allowed_user_id=?)",
                    (original.post_id, user_id),
                )
                if not self.cursor.fetchone()[0]:
                    return None

        if not content.strip():
            return None

        # 返信は posts に parent_post_id を設定して保存
        now = int(time.time())
        reply_post_id = str(uuid.uuid4())

        # ハッシュタグ・メンション抽出
        extracted_hashtags = self._extract_hashtags_from_content(content)
        extracted_mentions = self._extract_mentions_from_content(content)
        token_to_user_ids = self._resolve_mention_token_to_user_ids(extracted_mentions) if extracted_mentions else {}
        mentioned_user_ids_set = set(uid for ids in token_to_user_ids.values() for uid in ids)

        try:
            with self.db.transaction("IMMEDIATE"):
                # 返信投稿を作成（可視性は元投稿に合わせる）
                self.cursor.execute(
                    """
                    INSERT INTO posts (post_id, user_id, content, parent_post_id, visibility, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reply_post_id,
                        user_id,
                        content,
                        original.post_id,
                        original.visibility.value,
                        now,
                        now,
                    ),
                )

                # ハッシュタグ
                if extracted_hashtags:
                    self.cursor.executemany(
                        """
                        INSERT INTO post_hashtags (post_id, hashtag)
                        VALUES (?, ?)
                        """,
                        [(reply_post_id, tag) for tag in set(extracted_hashtags)],
                    )

                # メンションと通知
                if mentioned_user_ids_set:
                    mention_rows = [
                        (str(uuid.uuid4()), reply_post_id, user_id, mentioned_user_id, now)
                        for mentioned_user_id in mentioned_user_ids_set
                    ]
                    self.cursor.executemany(
                        """
                        INSERT INTO mentions (mention_id, post_id, mentioner_user_id, mentioned_user_id, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        mention_rows,
                    )
                    notification_rows = [
                        (
                            str(uuid.uuid4()),
                            mentioned_user_id,
                            user_id,
                            reply_post_id,
                            NotificationType.MENTION.value,
                            0,
                            now,
                        )
                        for mentioned_user_id in mentioned_user_ids_set
                    ]
                    self.cursor.executemany(
                        """
                        INSERT INTO notifications (notification_id, user_id, actor_id, post_id, notification_type, is_read, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        notification_rows,
                    )

                # 返信通知（自分の投稿以外）
                if original.user_id != user_id:
                    notification = Notification.create_reply_notification(
                        user_id=original.user_id,
                        from_user_id=user_id,
                        post_id=original.post_id,
                        reply_content=content,
                    )
                    self.cursor.execute(
                        """
                        INSERT INTO notifications (notification_id, user_id, actor_id, post_id, notification_type, is_read, created_at)
                        VALUES (?, ?, ?, ?, ?, 0, ?)
                        """,
                        (
                            notification.notification_id,
                            notification.user_id,
                            notification.from_user_id,
                            original.post_id,
                            notification.type.value,
                            int(notification.created_at.timestamp()),
                        ),
                    )

            # 戻り値はReplyデータ
            reply = Reply(
                reply_id=reply_post_id,
                user_id=user_id,
                post_id=post_id,
                content=content,
                created_at=datetime.fromtimestamp(now),
            )
            logger.info("reply_to_post: success reply_id=%s user_id=%s post_id=%s", reply_post_id, user_id, post_id)
            return reply
        except Exception:
            logger.exception("reply_to_post: failed user_id=%s post_id=%s", user_id, post_id)
            return None
    
    def get_post_replies(self, post_id: str, limit: int = 50) -> List[Reply]:
        """投稿の返信を取得（DB版）"""
        logger.debug("get_post_replies: post_id=%s limit=%d", post_id, limit)
        self.cursor.execute(
            """
            SELECT post_id, user_id, content, created_at
            FROM posts
            WHERE parent_post_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (post_id, limit),
        )
        rows = self.cursor.fetchall()
        logger.debug("get_post_replies: post_id=%s fetched=%d", post_id, len(rows))
        return [
            Reply(
                reply_id=row[0],
                user_id=row[1],
                post_id=post_id,
                content=row[2],
                created_at=datetime.fromtimestamp(row[3]),
            )
            for row in rows
        ]
    
    def get_post_replies_count(self, post_id: str) -> int:
        """投稿の返信数を取得（DB版）"""
        self.cursor.execute(
            "SELECT COUNT(*) FROM posts WHERE parent_post_id = ?",
            (post_id,),
        )
        count = int(self.cursor.fetchone()[0])
        logger.debug("get_post_replies_count: post_id=%s count=%d", post_id, count)
        return count
    
    # === 通知機能 ===
    def fetch_notifications_mark_read(self, user_id: str, limit: int = 50) -> List[Notification]:
        """通知を新しい順に取得し、同時に既読へ更新する。

        1. 最新から最大 limit 件の通知を取得
        2. 取得した notification_id をまとめて既読(is_read=1)に更新
        3. Notification のリストを返す
        """
        logger.debug("fetch_notifications_mark_read: user_id=%s limit=%d", user_id, limit)
        if limit <= 0:
            return []

        # 取得
        self.cursor.execute(
            """
            SELECT notification_id, user_id, actor_id, post_id, notification_type, is_read, created_at
            FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = self.cursor.fetchall()
        if not rows:
            logger.debug("fetch_notifications_mark_read: no rows user_id=%s", user_id)
            return []

        notification_ids = [row[0] for row in rows]

        # 既読化
        placeholders = ",".join(["?"] * len(notification_ids))
        with self.db.transaction("IMMEDIATE"):
            self.cursor.execute(
                f"UPDATE notifications SET is_read = 1 WHERE user_id = ? AND notification_id IN ({placeholders})",
                (user_id, *notification_ids),
            )
        logger.info("fetch_notifications_mark_read: marked_read=%d user_id=%s", len(notification_ids), user_id)

        # モデルに詰め替え
        result: List[Notification] = []
        for row in rows:
            notification_id, uid, actor_id, post_id, ntype, is_read, created_at = row
            result.append(
                Notification(
                    notification_id=notification_id,
                    user_id=uid,
                    type=NotificationType(ntype),
                    from_user_id=actor_id,
                    post_id=post_id,
                    content="",  # 既存テーブルはcontent列を保持していないため空文字
                    is_read=bool(is_read),
                    created_at=datetime.fromtimestamp(created_at),
                )
            )
        logger.debug("fetch_notifications_mark_read: returned=%d user_id=%s", len(result), user_id)
        return result

    def get_unread_notifications_count_db(self, user_id: str) -> int:
        """未読通知数（DB）"""
        self.cursor.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
            (user_id,),
        )
        count = int(self.cursor.fetchone()[0])
        logger.debug("get_unread_notifications_count_db: user_id=%s count=%d", user_id, count)
        return count
    
    def _find_user_by_name(self, name: str) -> Optional[str]:
        """ユーザー名からユーザーIDを検索（DB版、同名がいる場合は最古を返す）"""
        self.cursor.execute(
            """
            SELECT user_id
            FROM users
            WHERE name = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (name,),
        )
        row = self.cursor.fetchone()
        user_id = row[0] if row else None
        logger.debug("_find_user_by_name: name=%s user_id=%s", name, user_id)
        return user_id