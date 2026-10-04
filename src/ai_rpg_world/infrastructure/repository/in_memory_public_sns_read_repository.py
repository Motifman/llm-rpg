"""公開SNSの候補を、関連集合を複製せず上限付きで読む。"""

from __future__ import annotations

import copy
from heapq import nlargest

from ai_rpg_world.application.social.public_sns.contracts import ContentKind
from ai_rpg_world.application.social.public_sns.read_repository import PublicSnsContentRecord, PublicSnsUserRecord
from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.value_object.sns_identity_token import SnsIdentityToken
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore


def _validate_limit(limit: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 101:
        raise ValueError("取得件数は1から101までの整数で指定してください")


def _validate_kind(kind: ContentKind) -> None:
    if kind not in ("post", "reply"):
        raise ValueError("対象種別はpostまたはreplyで指定してください")


class InMemoryPublicSnsReadRepository:
    """閲覧可否は上位層へ委ね、内部整数ID降順の候補だけを返す。"""

    def __init__(self, data_store: InMemoryDataStore) -> None:
        self._data_store = data_store

    @property
    def namespace(self) -> str:
        return SnsIdentityToken(self._data_store.sns_public_namespace).value

    def find_user(self, user_id: int) -> PublicSnsUserRecord | None:
        user = self._data_store.sns_users.get(UserId(user_id))
        if user is None:
            return None
        return PublicSnsUserRecord(
            user_id=int(user.user_id), identity_token=SnsIdentityToken(user.identity_token).value,
            display_name=user.profile.display_name,
        )

    def has_block(self, blocker_user_id: int, blocked_user_id: int) -> bool:
        user = self._data_store.sns_users.get(UserId(blocker_user_id))
        return user is not None and user.is_blocked(UserId(blocked_user_id))

    @staticmethod
    def _record(kind: ContentKind, aggregate: PostAggregate | ReplyAggregate) -> PublicSnsContentRecord:
        parent_kind: ContentKind | None = None
        parent_id = None
        if aggregate.parent_reply_id is not None and aggregate.parent_post_id is None:
            parent_kind, parent_id = "reply", int(aggregate.parent_reply_id)
        elif aggregate.parent_post_id is not None and aggregate.parent_reply_id is None:
            parent_kind, parent_id = "post", int(aggregate.parent_post_id)
        return PublicSnsContentRecord(
            kind=kind,
            local_id=int(aggregate.content_id),
            identity_token=SnsIdentityToken(aggregate.identity_token).value,
            author_user_id=int(aggregate.author_user_id),
            content=aggregate.content.content,
            visibility=aggregate.content.visibility,
            deleted=aggregate.deleted,
            created_at=aggregate.created_at,
            parent_kind=parent_kind,
            parent_id=parent_id,
            author_identity_token=aggregate.author_identity_token,
            parent_identity_token=aggregate.parent_identity_token if kind == "reply" else None,
        )

    def find_content(self, kind: ContentKind, identity_token: str) -> PublicSnsContentRecord | None:
        _validate_kind(kind)
        candidates = self._data_store.posts.values() if kind == "post" else self._data_store.replies.values()
        found: PostAggregate | ReplyAggregate | None = None
        for aggregate in candidates:
            if aggregate.identity_token == identity_token:
                if found is not None:
                    return None
                found = aggregate
        return None if found is None else self._record(kind, found)

    def find_content_by_id(self, kind: ContentKind, local_id: int) -> PublicSnsContentRecord | None:
        _validate_kind(kind)
        aggregate = (
            self._data_store.posts.get(PostId(local_id))
            if kind == "post" else self._data_store.replies.get(ReplyId(local_id))
        )
        return None if aggregate is None else self._record(kind, aggregate)

    def scan_posts(self, before_id: int | None, limit: int) -> list[PublicSnsContentRecord]:
        _validate_limit(limit)
        candidates = (
            post for post in self._data_store.posts.values()
            if before_id is None or int(post.post_id) < before_id
        )
        bounded = nlargest(limit, candidates, key=lambda post: int(post.post_id))
        return [self._record("post", post) for post in bounded]

    def scan_replies(
        self, parent_kind: ContentKind, parent_id: int, before_id: int | None, limit: int,
    ) -> list[PublicSnsContentRecord]:
        _validate_limit(limit)
        _validate_kind(parent_kind)
        parent_reference = PostId(parent_id) if parent_kind == "post" else ReplyId(parent_id)
        candidates = (
            reply for reply in self._data_store.replies.values()
            if (before_id is None or int(reply.reply_id) < before_id)
            and (
                (parent_kind == "post" and reply.parent_post_id == parent_reference
                 and reply.parent_reply_id is None)
                or (parent_kind == "reply" and reply.parent_reply_id == parent_reference
                    and reply.parent_post_id is None)
            )
        )
        bounded = nlargest(limit, candidates, key=lambda reply: int(reply.reply_id))
        return [self._record("reply", reply) for reply in bounded]

    def scan_notifications(
        self, viewer_user_id: int, before_id: int | None, limit: int,
    ) -> list[Notification]:
        _validate_limit(limit)
        candidates = (
            notification for notification in self._data_store.sns_notifications.values()
            if int(notification.user_id) == viewer_user_id
            and (before_id is None or int(notification.notification_id) < before_id)
        )
        bounded = nlargest(limit, candidates, key=lambda notification: int(notification.notification_id))
        return [copy.deepcopy(notification) for notification in bounded]
