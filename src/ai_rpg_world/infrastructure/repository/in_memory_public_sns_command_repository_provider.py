"""公開SNS専用の、同じ作業領域へ参加するインメモリリポジトリ。"""
from __future__ import annotations

import copy
import heapq
from collections.abc import Callable
from typing import Any

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.social.public_sns.command_repository import PublicSnsCommandRepositories
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from ai_rpg_world.infrastructure.repository.in_memory_public_sns_read_repository import InMemoryPublicSnsReadRepository
from ai_rpg_world.infrastructure.repository.in_memory_reply_repository import InMemoryReplyRepository
from ai_rpg_world.infrastructure.repository.in_memory_sns_notification_repository import (
    InMemorySnsNotificationRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from ai_rpg_world.infrastructure.repository.scope_bound_repository import ScopeBoundRepository
from ai_rpg_world.infrastructure.unit_of_work.command_context_unit_of_work_facade import CommandContextUnitOfWorkFacade
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import unwrap_transaction


class _ImmediateScopedFacade(CommandContextUnitOfWorkFacade):
    """排他と全状態の復元を持つ作業領域へ即時反映し、読取模型も同じ状態を見る。"""

    def add_operation(self, operation: Callable[[], object]) -> None:
        if not self.is_in_transaction():
            raise CommandScopeStateException(current_state="closed", attempted_operation="write_public_sns")
        operation()


class InMemoryPublicSnsCommandRepositoryProvider:
    def __init__(self, unit_of_work: InMemoryUnitOfWork, context: CommandContext[PublicSnsCommandRepositories]) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        self._store = unit_of_work.data_store
        facade = _ImmediateScopedFacade(unit_of_work, context)
        self.posts = ScopeBoundRepository(InMemoryPostRepository(self._store, facade), self._require_active)
        self.replies = ScopeBoundRepository(InMemoryReplyRepository(self._store, facade), self._require_active)
        self.users = ScopeBoundRepository(InMemorySnsUserRepository(self._store, facade), self._require_active)
        self.notifications = ScopeBoundRepository(InMemorySnsNotificationRepository(self._store, facade), self._require_active)
        self.read = ScopeBoundRepository(InMemoryPublicSnsReadRepository(self._store), self._require_active)

    def _require_active(self) -> None:
        if not self._context.is_open or not self._unit_of_work.is_in_transaction():
            raise CommandScopeStateException(current_state="closed", attempted_operation="use_scoped_repository")

    def notification_exists(self, source_event_id: str, recipient_token: str, kind: str) -> bool:
        self._require_active()
        return any(n.source_event_id == source_event_id and n.recipient_identity_token == recipient_token
                   and n.notification_type.value == kind for n in self._store.sns_notifications.values())

    def pending_notifications(self, limit: int) -> list[Notification]:
        self._require_active()
        selected = heapq.nsmallest(
            limit,
            (n for n in self._store.sns_notifications.values()
             if n.source_event_id is not None and not n.observation_delivered),
            key=lambda n: n.notification_id.value,
        )
        return [copy.deepcopy(n) for n in selected]


class InMemoryPublicSnsCommandRepositoryProviderFactory:
    def create(self, context: CommandContext[PublicSnsCommandRepositories], transaction: TransactionPort) -> InMemoryPublicSnsCommandRepositoryProvider:
        adapter = unwrap_transaction(transaction)
        if not isinstance(adapter, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError("公開SNSにはInMemoryUnitOfWorkTransactionAdapterが必要です")
        return InMemoryPublicSnsCommandRepositoryProvider(adapter.unit_of_work, context)
