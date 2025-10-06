from dataclasses import dataclass
from src.domain.sns.enum import UserRelationshipType, PostVisibility
from typing import Optional


@dataclass(frozen=True)
class CreateUserCommand:
    """ユーザー作成コマンド"""
    user_name: str
    display_name: str
    bio: str


@dataclass(frozen=True)
class GetUserProfilesCommand:
    """ユーザープロフィール取得コマンド"""
    viewer_user_id: int
    relationship_type: UserRelationshipType


@dataclass(frozen=True)
class UpdateUserProfileCommand:
    """ユーザープロフィール更新コマンド"""
    user_id: int
    new_display_name: Optional[str] = None
    new_bio: Optional[str] = None


@dataclass(frozen=True)
class FollowUserCommand:
    """ユーザーフォローコマンド"""
    follower_user_id: int
    followee_user_id: int


@dataclass(frozen=True)
class UnfollowUserCommand:
    """ユーザーフォロー解除コマンド"""
    follower_user_id: int
    followee_user_id: int


@dataclass(frozen=True)
class BlockUserCommand:
    """ユーザーブロックコマンド"""
    blocker_user_id: int
    blocked_user_id: int


@dataclass(frozen=True)
class UnblockUserCommand:
    """ユーザーブロック解除コマンド"""
    blocker_user_id: int
    blocked_user_id: int


@dataclass(frozen=True)
class SubscribeUserCommand:
    """ユーザーサブスクライブコマンド"""
    subscriber_user_id: int
    subscribed_user_id: int


@dataclass(frozen=True)
class UnsubscribeUserCommand:
    """ユーザーサブスクライブ解除コマンド"""
    subscriber_user_id: int
    subscribed_user_id: int


@dataclass(frozen=True)
class CreatePostCommand:
    """ポスト作成コマンド"""
    user_id: int
    content: str
    visibility: PostVisibility = PostVisibility.PUBLIC


@dataclass(frozen=True)
class LikePostCommand:
    """ポストいいねコマンド"""
    post_id: int
    user_id: int


@dataclass(frozen=True)
class DeletePostCommand:
    """ポスト削除コマンド"""
    post_id: int
    user_id: int


@dataclass(frozen=True)
class CreateReplyCommand:
    """リプライ作成コマンド"""
    user_id: int
    content: str
    visibility: PostVisibility = PostVisibility.PUBLIC
    parent_post_id: Optional[int] = None
    parent_reply_id: Optional[int] = None


@dataclass(frozen=True)
class LikeReplyCommand:
    """リプライいいねコマンド"""
    reply_id: int
    user_id: int


@dataclass(frozen=True)
class DeleteReplyCommand:
    """リプライ削除コマンド"""
    reply_id: int
    user_id: int


@dataclass(frozen=True)
class MarkNotificationAsReadCommand:
    """通知既読コマンド"""
    notification_id: int


@dataclass(frozen=True)
class MarkAllNotificationsAsReadCommand:
    """全通知既読コマンド"""
    user_id: int