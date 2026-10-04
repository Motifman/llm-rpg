"""公開SNSの本文と継続取得を、内部の整数IDを出さずに受け渡す。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ContentKind = Literal["post", "reply"]


class PublicSnsUnavailableError(Exception):
    """存在しない対象と閲覧できない対象を同じ応答にする。"""

    def __init__(self) -> None:
        super().__init__("この投稿は現在表示できません")


class PublicSnsInvalidRequestError(Exception):
    """対象の存在に依存しない入力の誤りを示す。"""


@dataclass(frozen=True)
class PublicSnsContentDto:
    target_id: str
    kind: ContentKind
    author_display_name: str
    content: str
    created_at: datetime
    author_target_id: str
    parent_target_id: str | None = None


@dataclass(frozen=True)
class PublicSnsPage:
    items: tuple[PublicSnsContentDto, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class PublicSnsThread:
    selected: PublicSnsContentDto
    replies: PublicSnsPage
    ancestors: tuple[PublicSnsContentDto, ...] = ()


@dataclass(frozen=True)
class PublicSnsNotificationDto:
    kind: str
    actor_display_name: str
    created_at: datetime
    notification_id: str
    actor_target_id: str
    target_id: str | None = None
    content: str | None = None


@dataclass(frozen=True)
class PublicSnsNotificationPage:
    items: tuple[PublicSnsNotificationDto, ...]
    next_cursor: str | None = None
