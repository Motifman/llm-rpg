"""公開SNSコマンドが同じ確定境界から受け取るリポジトリ束。"""
from __future__ import annotations

from typing import Protocol

from ai_rpg_world.application.social.public_sns.read_repository import PublicSnsReadRepository
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.domain.sns.repository.post_repository import PostRepository
from ai_rpg_world.domain.sns.repository.reply_repository import ReplyRepository
from ai_rpg_world.domain.sns.repository.sns_notification_repository import SnsNotificationRepository
from ai_rpg_world.domain.sns.repository.sns_user_repository import UserRepository


class PublicSnsCommandRepositories(Protocol):
    @property
    def posts(self) -> PostRepository: ...
    @property
    def replies(self) -> ReplyRepository: ...
    @property
    def users(self) -> UserRepository: ...
    @property
    def notifications(self) -> SnsNotificationRepository: ...
    @property
    def read(self) -> PublicSnsReadRepository: ...

    def notification_exists(self, source_event_id: str, recipient_token: str, kind: str) -> bool: ...
    def pending_notifications(self, limit: int, *, after_id: int = 0) -> list[Notification]: ...
