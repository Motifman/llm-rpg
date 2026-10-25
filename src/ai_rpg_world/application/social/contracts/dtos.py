from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class UserProfileDto:
    user_id: int
    user_name: str
    display_name: str
    bio: str
    is_following: bool | None  # 自分の場合はNone
    is_followed_by: bool | None  # 自分の場合はNone
    is_blocked: bool | None  # 自分の場合はNone
    is_blocked_by: bool | None  # 自分の場合はNone
    is_subscribed: bool | None  # 自分の場合はNone
    is_subscribed_by: bool | None  # 自分の場合はNone
    followee_count: int
    follower_count: int


@dataclass(frozen=True)
class ErrorResponseDto:
    """エラーレスポンスDTO"""

    error_code: str
    message: str
    details: str | None = None
    user_id: int | None = None
    target_user_id: int | None = None


@dataclass(frozen=True)
class UserQueryResultDto:
    """ユーザー検索結果DTO（成功・失敗両方を含む）"""

    success: bool
    data: list[UserProfileDto] | None = None
    error: ErrorResponseDto | None = None


@dataclass(frozen=True)
class PostDto:
    """ポスト表示用DTO"""

    post_id: int
    author_user_id: int
    author_user_name: str
    author_display_name: str
    content: str
    hashtags: list[str]
    visibility: str
    created_at: datetime
    like_count: int
    reply_count: int
    is_liked_by_viewer: bool
    is_replied_by_viewer: bool
    mentioned_users: list[str]
    is_deleted: bool
    deletion_message: str | None = None

    def get_sort_key_by_created_at(self) -> datetime:
        """ソート用の作成日時を取得"""
        return self.created_at


@dataclass(frozen=True)
class ReplyDto:
    """リプライ表示用DTO"""

    reply_id: int
    parent_post_id: int | None  # 親ポストID
    parent_reply_id: int | None  # 親リプライID（ネスト用）
    author_user_id: int
    author_user_name: str
    author_display_name: str
    content: str
    hashtags: list[str]
    visibility: str
    created_at: datetime
    like_count: int
    is_liked_by_viewer: bool
    mentioned_users: list[str]
    is_deleted: bool
    deletion_message: str | None = None
    # ツリー構造表示用の情報
    depth: int = 0  # ネストの深さ
    has_replies: bool = False  # 子リプライがあるかどうか
    reply_count: int = 0  # 子リプライの数

    def get_sort_key_by_created_at(self) -> datetime:
        """ソート用の作成日時を取得"""
        return self.created_at


@dataclass(frozen=True)
class ReplyThreadDto:
    """リプライスレッド表示用DTO（ポスト＋リプライツリー）"""

    post: PostDto
    replies: list[ReplyDto]  # フラットなリプライ一覧（ツリー構造はdepthで表現）


@dataclass(frozen=True)
class NotificationDto:
    """通知表示用DTO"""

    notification_id: int
    user_id: int
    notification_type: str
    title: str
    message: str
    actor_user_id: int
    actor_user_name: str
    created_at: datetime
    is_read: bool
    related_post_id: int | None = None
    related_reply_id: int | None = None
    content_type: str | None = None
    content_text: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class CommandResultDto:
    """コマンド実行結果DTO"""

    success: bool
    message: str | None = None
    data: dict[str, Any] | None = None  # 作成されたユーザーIDなど
