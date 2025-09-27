from dataclasses import dataclass
from typing import Optional, List


@dataclass(frozen=True)
class UserProfileDto:
    user_id: int
    user_name: str
    display_name: str
    bio: str
    is_following: Optional[bool]  # 自分の場合はNone
    is_followed_by: Optional[bool]  # 自分の場合はNone
    is_blocked: Optional[bool]  # 自分の場合はNone
    is_blocked_by: Optional[bool]  # 自分の場合はNone
    is_subscribed: Optional[bool]  # 自分の場合はNone
    is_subscribed_by: Optional[bool]  # 自分の場合はNone
    followee_count: int
    follower_count: int


@dataclass(frozen=True)
class ErrorResponseDto:
    """エラーレスポンスDTO"""
    error_code: str
    message: str
    details: Optional[str] = None
    user_id: Optional[int] = None
    target_user_id: Optional[int] = None


@dataclass(frozen=True)
class UserQueryResultDto:
    """ユーザー検索結果DTO（成功・失敗両方を含む）"""
    success: bool
    data: Optional[List[UserProfileDto]] = None
    error: Optional[ErrorResponseDto] = None


@dataclass(frozen=True)
class CommandResultDto:
    """コマンド実行結果DTO"""
    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None  # 作成されたユーザーIDなど