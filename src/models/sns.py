from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class NotificationType(Enum):
    """通知タイプ"""
    FOLLOW = "follow"
    LIKE = "like"
    REPLY = "reply"


@dataclass(frozen=True)
class SnsUser:
    """SNSユーザー"""
    user_id: str
    name: str
    bio: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    
    def __str__(self):
        return f"SnsUser(user_id={self.user_id}, name={self.name})"
    
    def __repr__(self):
        return f"SnsUser(user_id={self.user_id}, name={self.name}, bio={self.bio})"


@dataclass(frozen=True)
class Post:
    """投稿"""
    post_id: str
    user_id: str
    content: str
    hashtags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def create(cls, user_id: str, content: str, hashtags: Optional[List[str]] = None) -> "Post":
        """新しい投稿を作成"""
        return cls(
            post_id=str(uuid.uuid4()),
            user_id=user_id,
            content=content,
            hashtags=hashtags or [],
        )
    
    def extract_hashtags_from_content(self) -> List[str]:
        """投稿内容からハッシュタグを抽出"""
        import re
        hashtag_pattern = r'#\w+'
        return re.findall(hashtag_pattern, self.content)
    
    def __str__(self):
        return f"Post(post_id={self.post_id}, user_id={self.user_id}, content={self.content[:50]}...)"
    
    def __repr__(self):
        return f"Post(post_id={self.post_id}, user_id={self.user_id}, content={self.content})"


@dataclass(frozen=True)
class Follow:
    """フォロー関係"""
    follower_id: str  # フォローする人
    following_id: str  # フォローされる人
    created_at: datetime = field(default_factory=datetime.now)
    
    def __str__(self):
        return f"Follow(follower={self.follower_id}, following={self.following_id})"
    
    def __repr__(self):
        return f"Follow(follower_id={self.follower_id}, following_id={self.following_id})"


@dataclass(frozen=True)
class Block:
    """ブロック関係"""
    blocker_id: str  # ブロックする人
    blocked_id: str  # ブロックされる人
    created_at: datetime = field(default_factory=datetime.now)
    
    def __str__(self):
        return f"Block(blocker={self.blocker_id}, blocked={self.blocked_id})"
    
    def __repr__(self):
        return f"Block(blocker_id={self.blocker_id}, blocked_id={self.blocked_id})"


@dataclass(frozen=True)
class Like:
    """いいね"""
    like_id: str
    user_id: str
    post_id: str
    created_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def create(cls, user_id: str, post_id: str) -> "Like":
        """新しいいいねを作成"""
        return cls(
            like_id=str(uuid.uuid4()),
            user_id=user_id,
            post_id=post_id,
        )
    
    def __str__(self):
        return f"Like(user_id={self.user_id}, post_id={self.post_id})"
    
    def __repr__(self):
        return f"Like(like_id={self.like_id}, user_id={self.user_id}, post_id={self.post_id})"


@dataclass(frozen=True)
class Reply:
    """返信"""
    reply_id: str
    user_id: str
    post_id: str
    content: str
    created_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def create(cls, user_id: str, post_id: str, content: str) -> "Reply":
        """新しい返信を作成"""
        return cls(
            reply_id=str(uuid.uuid4()),
            user_id=user_id,
            post_id=post_id,
            content=content,
        )
    
    def __str__(self):
        return f"Reply(user_id={self.user_id}, post_id={self.post_id}, content={self.content[:30]}...)"
    
    def __repr__(self):
        return f"Reply(reply_id={self.reply_id}, user_id={self.user_id}, post_id={self.post_id}, content={self.content})"


@dataclass(frozen=True)
class Notification:
    """通知"""
    notification_id: str
    user_id: str  # 通知対象者
    type: NotificationType
    from_user_id: str  # 通知元ユーザー
    post_id: Optional[str] = None  # 関連投稿ID
    content: str = ""
    is_read: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def create_follow_notification(cls, user_id: str, from_user_id: str) -> "Notification":
        """フォロー通知を作成"""
        return cls(
            notification_id=str(uuid.uuid4()),
            user_id=user_id,
            type=NotificationType.FOLLOW,
            from_user_id=from_user_id,
            content=f"{from_user_id}があなたをフォローしました",
        )
    
    @classmethod
    def create_like_notification(cls, user_id: str, from_user_id: str, post_id: str) -> "Notification":
        """いいね通知を作成"""
        return cls(
            notification_id=str(uuid.uuid4()),
            user_id=user_id,
            type=NotificationType.LIKE,
            from_user_id=from_user_id,
            post_id=post_id,
            content=f"{from_user_id}があなたの投稿にいいねしました",
        )
    
    @classmethod
    def create_reply_notification(cls, user_id: str, from_user_id: str, post_id: str, reply_content: str) -> "Notification":
        """返信通知を作成"""
        return cls(
            notification_id=str(uuid.uuid4()),
            user_id=user_id,
            type=NotificationType.REPLY,
            from_user_id=from_user_id,
            post_id=post_id,
            content=f"{from_user_id}があなたの投稿に返信しました: {reply_content[:30]}...",
        )
    
    def mark_as_read(self) -> "Notification":
        """既読としてマーク（新しいインスタンスを返す）"""
        from dataclasses import replace
        return replace(self, is_read=True)
    
    def __str__(self):
        return f"Notification(user_id={self.user_id}, type={self.type.value}, from={self.from_user_id})"
    
    def __repr__(self):
        return f"Notification(notification_id={self.notification_id}, user_id={self.user_id}, type={self.type}, content={self.content})" 