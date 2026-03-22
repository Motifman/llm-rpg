"""LLM 向け仮想 SNS 画面スナップショット DTO（内部 ID は載せない）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from ai_rpg_world.application.social.sns_virtual_pages.kinds import (
    SnsHomeTab,
    SnsSearchMode,
    SnsVirtualPageKind,
)


@dataclass(frozen=True)
class SnsPagingSnapshotDto:
    """ページング摘要（offset / limit / has_more）。"""

    offset: int
    limit: int
    has_more: bool


@dataclass(frozen=True)
class SnsPostLineSnapshotDto:
    """タイムライン等の 1 行（投稿）。post_ref / author_user_ref のみで参照する。"""

    author_display_name: str
    content_preview: str
    created_at: datetime
    like_count: int
    reply_count: int
    is_liked_by_viewer: bool
    is_replied_by_viewer: bool
    post_ref: str
    author_user_ref: Optional[str] = None


@dataclass(frozen=True)
class SnsReplyLineSnapshotDto:
    """post_detail の 1 行（返信）。"""

    author_display_name: str
    content_preview: str
    created_at: datetime
    depth: int
    like_count: int
    reply_count: int
    is_liked_by_viewer: bool
    reply_ref: str
    author_user_ref: Optional[str] = None


@dataclass(frozen=True)
class SnsPostDetailSnapshotDto:
    """post_detail: ルート投稿＋返信フラット一覧。"""

    root_post: SnsPostLineSnapshotDto
    replies: List[SnsReplyLineSnapshotDto] = field(default_factory=list)


@dataclass(frozen=True)
class SnsHomeSnapshotDto:
    """home: タブ＋投稿行＋任意でトレンドタグ。"""

    active_tab: SnsHomeTab
    posts: List[SnsPostLineSnapshotDto] = field(default_factory=list)
    trending_hashtags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SnsSearchSnapshotDto:
    """search: モード・クエリ・結果。"""

    search_mode: Optional[SnsSearchMode]
    search_query: str
    posts: List[SnsPostLineSnapshotDto] = field(default_factory=list)


@dataclass(frozen=True)
class SnsProfileHeaderSnapshotDto:
    """profile: ヘッダ（user_id は出さない）。"""

    display_name: str
    user_name: str
    bio: str
    is_self: bool
    followee_count: int
    follower_count: int
    is_following: Optional[bool]
    is_followed_by: Optional[bool]
    is_blocked: Optional[bool]
    is_blocked_by: Optional[bool]
    is_subscribed: Optional[bool]
    is_subscribed_by: Optional[bool]
    subject_user_ref: Optional[str] = None


@dataclass(frozen=True)
class SnsProfileSnapshotDto:
    """profile: ヘッダ＋そのユーザーの投稿一覧。"""

    header: SnsProfileHeaderSnapshotDto
    posts: List[SnsPostLineSnapshotDto] = field(default_factory=list)


@dataclass(frozen=True)
class SnsNotificationLineSnapshotDto:
    """notifications: 1 行。"""

    notification_type: str
    title: str
    message: str
    created_at: datetime
    is_read: bool
    notification_ref: str
    actor_user_ref: Optional[str] = None
    related_post_ref: Optional[str] = None
    related_reply_ref: Optional[str] = None


@dataclass(frozen=True)
class SnsNotificationsSnapshotDto:
    """notifications: 一覧＋未読数（数値のみ）。"""

    notifications: List[SnsNotificationLineSnapshotDto] = field(default_factory=list)
    unread_count: int = 0


@dataclass(frozen=True)
class SnsVirtualPageSnapshotDto:
    """現在画面のスナップショット。page_kind に応じて対応する *_ フィールドのみ使用。"""

    page_kind: SnsVirtualPageKind
    snapshot_generation: int
    paging: SnsPagingSnapshotDto
    error: Optional[str] = None
    home: Optional[SnsHomeSnapshotDto] = None
    post_detail: Optional[SnsPostDetailSnapshotDto] = None
    search: Optional[SnsSearchSnapshotDto] = None
    profile: Optional[SnsProfileSnapshotDto] = None
    notifications: Optional[SnsNotificationsSnapshotDto] = None


__all__ = [
    "SnsPagingSnapshotDto",
    "SnsPostLineSnapshotDto",
    "SnsReplyLineSnapshotDto",
    "SnsPostDetailSnapshotDto",
    "SnsHomeSnapshotDto",
    "SnsSearchSnapshotDto",
    "SnsProfileHeaderSnapshotDto",
    "SnsProfileSnapshotDto",
    "SnsNotificationLineSnapshotDto",
    "SnsNotificationsSnapshotDto",
    "SnsVirtualPageSnapshotDto",
]
