"""既存の画面参照に依存せず、公開SNSだけを有限件ずつ取得する。"""
from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from datetime import datetime
from typing import TypeVar

from ai_rpg_world.application.social.public_sns.access_policy import PublicSnsAccessPolicy
from ai_rpg_world.application.social.public_sns.contracts import (
    PublicSnsContentDto,
    PublicSnsInvalidRequestError,
    PublicSnsNotificationDto,
    PublicSnsNotificationPage,
    PublicSnsPage,
    PublicSnsThread,
    PublicSnsUnavailableError,
)
from ai_rpg_world.application.social.public_sns.read_repository import (
    PublicSnsContentRecord,
    PublicSnsReadRepository,
)
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.value_object.notification_type import NotificationType

T = TypeVar("T")
R = TypeVar("R")
MAX_PUBLIC_SNS_PAGE_SIZE = 20
PUBLIC_SNS_SCAN_BUDGET = 100


class PublicSnsReadService:
    """一覧は最大100候補を検査し、残りがあれば空ページでも継続位置を返す。"""

    def __init__(
        self,
        repository: PublicSnsReadRepository,
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._repository = repository
        self._access = PublicSnsAccessPolicy(repository)
        self._now = now

    def read_posts(
        self, viewer_user_id: int, *, cursor: str | None = None, limit: int = 10
    ) -> PublicSnsPage:
        binding = self._binding(viewer_user_id, "posts")
        before = self._validate_request(viewer_user_id, cursor, limit, binding)
        rows = self._repository.scan_posts(before, PUBLIC_SNS_SCAN_BUDGET + 1)
        items, following = self._page(
            rows, limit, binding, lambda row: row.local_id,
            lambda row: self._visible_dto(viewer_user_id, row),
        )
        return PublicSnsPage(items, following)

    def read_target(
        self,
        viewer_user_id: int,
        target_id: str,
        *,
        cursor: str | None = None,
        limit: int = 10,
    ) -> PublicSnsThread:
        binding = self._binding(viewer_user_id, "thread", target_id)
        before = self._validate_request(viewer_user_id, cursor, limit, binding)
        selected = self._access.require_visible_target(viewer_user_id, target_id)
        rows = self._repository.scan_replies(
            selected.kind, selected.local_id, before, PUBLIC_SNS_SCAN_BUDGET + 1
        )
        items, following = self._page(
            rows, limit, binding, lambda row: row.local_id,
            lambda row: self._visible_dto(viewer_user_id, row),
        )
        chain = self._access.visible_chain(viewer_user_id, selected)
        if chain is None:
            raise PublicSnsUnavailableError()
        return PublicSnsThread(
            self._dto(selected), PublicSnsPage(items, following),
            tuple(self._dto(ancestor) for ancestor in reversed(chain[1:])),
        )

    def read_notifications(
        self, viewer_user_id: int, *, cursor: str | None = None, limit: int = 10
    ) -> PublicSnsNotificationPage:
        binding = self._binding(viewer_user_id, "inbox")
        before = self._validate_request(viewer_user_id, cursor, limit, binding)
        rows = self._repository.scan_notifications(
            viewer_user_id, before, PUBLIC_SNS_SCAN_BUDGET + 1
        )
        items, following = self._page(
            rows, limit, binding, lambda row: row.notification_id.value,
            lambda row: self.visible_notification(viewer_user_id, row),
        )
        return PublicSnsNotificationPage(items, following)

    def visible_notification(
        self, viewer_user_id: int, notification: Notification
    ) -> PublicSnsNotificationDto | None:
        """保存済み本文を信用せず、配送直前にも現在の公開条件を検査できる。"""
        if notification.user_id.value != viewer_user_id or notification.is_expired(self._now()):
            return None
        content = notification.content
        if not self._access.users_can_interact(viewer_user_id, content.actor_user_id.value):
            return None
        actor = self._repository.find_user(content.actor_user_id.value)
        viewer = self._repository.find_user(viewer_user_id)
        if (
            actor is None
            or viewer is None
            or content.actor_identity_token != actor.identity_token
            or notification.recipient_identity_token != viewer.identity_token
        ):
            return None
        target: PublicSnsContentRecord | None = None
        if content.related_target_id is not None:
            try:
                target = self._access.require_visible_target(viewer_user_id, content.related_target_id)
            except PublicSnsUnavailableError:
                return None
        if notification.notification_type is not NotificationType.FOLLOW and target is None:
            return None
        # 通知の旧整数参照が不変IDと異なる場合も、別投稿へ結び直さない。
        if target is not None:
            if content.related_reply_id is not None and (
                target.kind != "reply" or target.local_id != content.related_reply_id.value
            ):
                return None
            if content.related_post_id is not None:
                post = self._repository.find_content_by_id("post", content.related_post_id.value)
                if post is None or not self._access.can_view(viewer_user_id, post):
                    return None
                chain = self._access.visible_chain(viewer_user_id, target)
                if chain is None or chain[-1].identity_token != post.identity_token:
                    return None
        show_body = notification.notification_type in {NotificationType.REPLY, NotificationType.MENTION}
        return PublicSnsNotificationDto(
            notification_id=f"sns:{self._repository.namespace}:notification:{notification.identity_token}",
            actor_target_id=f"sns:{self._repository.namespace}:user:{actor.identity_token}",
            kind=notification.notification_type.value,
            actor_display_name=actor.display_name,
            created_at=notification.created_at,
            target_id=self._access.target_id(target) if target else None,
            content=target.content if target is not None and show_body else None,
        )

    def _visible_dto(self, viewer_user_id: int, row: PublicSnsContentRecord) -> PublicSnsContentDto | None:
        return self._dto(row) if self._access.can_view(viewer_user_id, row) else None

    def _dto(self, row: PublicSnsContentRecord) -> PublicSnsContentDto:
        author = self._repository.find_user(row.author_user_id)
        if author is None:
            raise PublicSnsUnavailableError()
        parent = None
        if row.parent_kind is not None and row.parent_id is not None:
            parent = self._repository.find_content_by_id(row.parent_kind, row.parent_id)
        return PublicSnsContentDto(
            target_id=self._access.target_id(row),
            kind=row.kind,
            author_display_name=author.display_name,
            author_target_id=f"sns:{self._repository.namespace}:user:{author.identity_token}",
            content=row.content,
            created_at=row.created_at,
            parent_target_id=self._access.target_id(parent) if parent else None,
        )

    def _binding(self, viewer: int, view: str, target: str | None = None) -> list[object]:
        user = self._repository.find_user(viewer)
        if user is None:
            raise PublicSnsUnavailableError()
        return [self._repository.namespace, user.identity_token, view, target]

    def _validate_request(
        self, viewer: int, cursor: str | None, limit: int, binding: list[object]
    ) -> int | None:
        if type(limit) is not int or not 1 <= limit <= MAX_PUBLIC_SNS_PAGE_SIZE:
            raise PublicSnsInvalidRequestError("取得件数は1から20で指定してください")
        if self._repository.find_user(viewer) is None:
            raise PublicSnsUnavailableError()
        if cursor is None:
            return None
        try:
            if not isinstance(cursor, str) or not cursor.startswith("sns-page:") or len(cursor) > 2048:
                raise ValueError
            raw = base64.b64decode(cursor[9:].encode("ascii"), altchars=b"-_", validate=True)
            data = json.loads(raw)
            if not isinstance(data, list) or len(data) != 2 or data[0] != binding:
                raise ValueError
            before = data[1]
            if type(before) is not int or not 1 <= before <= 2**63 - 1:
                raise ValueError
            return before
        except (ValueError, TypeError, UnicodeError, binascii.Error):
            raise PublicSnsInvalidRequestError("継続位置が無効です。先頭から取得してください") from None

    def _page(
        self,
        rows: list[T],
        limit: int,
        binding: list[object],
        local_id: Callable[[T], int],
        convert: Callable[[T], R | None],
    ) -> tuple[tuple[R, ...], str | None]:
        output: list[R] = []
        examined = 0
        for row in rows[:PUBLIC_SNS_SCAN_BUDGET]:
            examined += 1
            visible = convert(row)
            if visible is not None:
                output.append(visible)
                if len(output) == limit:
                    break
        cursor = None
        if examined < len(rows):
            data = [binding, local_id(rows[examined - 1])]
            cursor = "sns-page:" + base64.urlsafe_b64encode(
                json.dumps(data, separators=(",", ":")).encode("utf-8")
            ).decode("ascii")
        return tuple(output), cursor
