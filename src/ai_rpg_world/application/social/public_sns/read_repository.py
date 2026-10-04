"""公開SNS専用の小さい読取模型。関連する全返信や全いいねは復元しない。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ai_rpg_world.application.social.public_sns.contracts import ContentKind
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.enum.sns_enum import PostVisibility


@dataclass(frozen=True)
class PublicSnsUserRecord:
    user_id: int
    identity_token: str
    display_name: str


@dataclass(frozen=True)
class PublicSnsContentRecord:
    kind: ContentKind
    local_id: int
    identity_token: str
    author_user_id: int
    content: str
    visibility: PostVisibility
    deleted: bool
    created_at: datetime
    parent_kind: ContentKind | None = None
    parent_id: int | None = None
    author_identity_token: str | None = None
    parent_identity_token: str | None = None


class PublicSnsReadRepository(Protocol):
    """呼出しごとの取得件数を制限し、整数ID降順の継続取得を提供する。"""

    @property
    def namespace(self) -> str: ...

    def find_user(self, user_id: int) -> PublicSnsUserRecord | None: ...

    def has_block(self, blocker_user_id: int, blocked_user_id: int) -> bool: ...

    def find_content(self, kind: ContentKind, identity_token: str) -> PublicSnsContentRecord | None: ...

    def find_content_by_id(self, kind: ContentKind, local_id: int) -> PublicSnsContentRecord | None: ...

    def scan_posts(self, before_id: int | None, limit: int) -> list[PublicSnsContentRecord]: ...

    def scan_replies(self, parent_kind: ContentKind, parent_id: int, before_id: int | None, limit: int) -> list[PublicSnsContentRecord]: ...

    def scan_notifications(self, viewer_user_id: int, before_id: int | None, limit: int) -> list[Notification]: ...
