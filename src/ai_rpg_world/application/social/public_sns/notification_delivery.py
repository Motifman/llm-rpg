"""確定済み通知だけを配送し、失敗した観測を保存済み通知から再送する。"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactoryPort
from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance
from ai_rpg_world.application.social.public_sns.command_repository import PublicSnsCommandRepositories
from ai_rpg_world.application.social.public_sns.contracts import PublicSnsNotificationDto
from ai_rpg_world.application.social.public_sns.notification_events import (
    PublicSnsActivityEvent,
    PublicSnsNotificationReadyEvent,
)
from ai_rpg_world.application.social.public_sns.read_service import PublicSnsReadService
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId

NotificationDelivery = Callable[[int, PublicSnsNotificationDto, ExecutionProvenance | None], None]


class PublicSnsAfterCommitHandoff:
    """投稿の確定後に現在の公開条件を検査する。本文と出典は再送可能な通知に残す。"""

    def __init__(self, deliver_notification: NotificationDelivery | None = None) -> None:
        self._deliver_notification = deliver_notification
        self._scope_factory: CommandScopeFactoryPort[PublicSnsCommandRepositories] | None = None

    def bind_scope_factory(self, factory: CommandScopeFactoryPort[PublicSnsCommandRepositories]) -> None:
        if self._scope_factory is not None:
            raise RuntimeError("配送先の確定境界は一度だけ設定できます")
        self._scope_factory = factory

    def handoff(self, events: Sequence[DomainEvent]) -> None:
        if self._deliver_notification is None:
            return
        for event in events:
            if isinstance(event, PublicSnsNotificationReadyEvent):
                self._deliver(event.notification_id, event.notification_identity_token)

    def _deliver(self, notification_id: int, identity_token: str) -> bool:
        assert self._scope_factory is not None
        assert self._deliver_notification is not None
        with self._scope_factory.create() as context:
            repos = context.repositories
            notification = repos.notifications.find_by_id(NotificationId(notification_id))
            if notification is None or notification.identity_token != identity_token or notification.observation_delivered:
                return False
            dto = PublicSnsReadService(repos.read).visible_notification(notification.user_id.value, notification)
            provenance_data = notification.execution_provenance
            provenance = ExecutionProvenance.from_dict(provenance_data) if provenance_data else None
        # 独立した読取scopeも閉じてから、取り消せない観測側へ渡す。
        # 受信側はdto.notification_idで冪等に扱う（配送直後の停止でも重複適用しない）。
        if dto is not None:
            self._deliver_notification(notification.user_id.value, dto, provenance)
        with self._scope_factory.create() as context:
            current = context.repositories.notifications.find_by_id(NotificationId(notification_id))
            if current is not None and current.identity_token == identity_token:
                current.mark_observation_delivered()
                context.repositories.notifications.save(current)
        return dto is not None

    def retry_pending(self, *, limit: int = 100) -> int:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("再送件数は1から100で指定してください")
        if self._deliver_notification is None:
            return 0
        assert self._scope_factory is not None
        with self._scope_factory.create() as context:
            pending = context.repositories.pending_notifications(limit)
        return sum(self._deliver(n.notification_id.value, n.identity_token) for n in pending)


class PublicSnsIncomingNotificationService:
    """すでに不変IDへ束縛された受信イベントを、新しい確定境界で処理する。"""

    def __init__(self, scope_factory: CommandScopeFactoryPort[PublicSnsCommandRepositories]) -> None:
        self._scope_factory = scope_factory

    def record_activity(self, event: PublicSnsActivityEvent) -> None:
        with self._scope_factory.create() as context:
            context.collect(event)
