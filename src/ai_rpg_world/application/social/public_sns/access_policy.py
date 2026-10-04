"""公開SNSの新規取得と操作に共通する、祖先を含む閲覧判定。"""
from __future__ import annotations

import logging
import re

from ai_rpg_world.application.social.public_sns.contracts import ContentKind, PublicSnsUnavailableError
from ai_rpg_world.application.social.public_sns.read_repository import (
    PublicSnsContentRecord,
    PublicSnsReadRepository,
    PublicSnsUserRecord,
)
from ai_rpg_world.domain.sns.enum.sns_enum import PostVisibility

_TARGET = re.compile(r"sns:([0-9a-f]{32}):(post|reply):([0-9a-f]{32})\Z")
MAX_PUBLIC_SNS_ANCESTORS = 64
_logger = logging.getLogger(__name__)


class PublicSnsAccessPolicy:
    """本人の投稿でも非公開なら除き、全祖先で削除と双方向ブロックを検査する。"""

    def __init__(self, repository: PublicSnsReadRepository) -> None:
        self._repository = repository

    def target_id(self, record: PublicSnsContentRecord) -> str:
        return f"sns:{self._repository.namespace}:{record.kind}:{record.identity_token}"

    def require_visible_target(
        self, viewer_user_id: int, target_id: str
    ) -> PublicSnsContentRecord:
        match = _TARGET.fullmatch(target_id) if isinstance(target_id, str) else None
        if match is None or match[1] != self._repository.namespace:
            raise PublicSnsUnavailableError()
        kind: ContentKind = "post" if match[2] == "post" else "reply"
        record = self._repository.find_content(kind, match[3])
        if record is None or not self.can_view(viewer_user_id, record):
            raise PublicSnsUnavailableError()
        return record

    def users_can_interact(self, viewer_user_id: int, author_user_id: int) -> bool:
        viewer = self._repository.find_user(viewer_user_id)
        author = self._repository.find_user(author_user_id)
        return bool(
            viewer is not None
            and author is not None
            and not self._repository.has_block(viewer_user_id, author_user_id)
            and not self._repository.has_block(author_user_id, viewer_user_id)
        )

    def can_view(self, viewer_user_id: int, record: PublicSnsContentRecord) -> bool:
        return self.visible_chain(viewer_user_id, record) is not None

    def visible_chain(
        self, viewer_user_id: int, record: PublicSnsContentRecord
    ) -> tuple[PublicSnsContentRecord, ...] | None:
        """選択対象から根までの検査済み祖先を返し、不正な鎖は全体を拒む。"""
        viewer = self._repository.find_user(viewer_user_id)
        if viewer is None:
            return None
        authors: dict[int, PublicSnsUserRecord | None] = {}
        blocked: dict[int, bool] = {}
        seen: set[tuple[str, int]] = set()
        chain: list[PublicSnsContentRecord] = []
        current = record
        for _ in range(MAX_PUBLIC_SNS_ANCESTORS):
            key = (current.kind, current.local_id)
            if key in seen:
                _logger.warning("公開SNSの祖先参照が循環しています", extra={"content_kind": current.kind, "local_id": current.local_id})
                return None
            seen.add(key)
            chain.append(current)
            if current.author_user_id not in authors:
                authors[current.author_user_id] = self._repository.find_user(current.author_user_id)
                blocked[current.author_user_id] = authors[current.author_user_id] is None or (
                    self._repository.has_block(viewer_user_id, current.author_user_id)
                    or self._repository.has_block(current.author_user_id, viewer_user_id)
                )
            author = authors[current.author_user_id]
            if (
                current.deleted
                or current.visibility is not PostVisibility.PUBLIC
                or author is None
                or current.author_identity_token != author.identity_token
                or blocked[current.author_user_id]
            ):
                return None
            if current.kind == "post":
                return tuple(chain) if current.parent_kind is None and current.parent_id is None else None
            if current.parent_kind is None or current.parent_id is None:
                return None
            parent = self._repository.find_content_by_id(current.parent_kind, current.parent_id)
            if parent is None or current.parent_identity_token != parent.identity_token:
                return None
            current = parent
        # 不正な循環や過剰な深さから、制限のない祖先取得へ進まない。
        _logger.warning("公開SNSの祖先参照が取得上限を超えました", extra={"content_kind": record.kind, "local_id": record.local_id})
        return None
