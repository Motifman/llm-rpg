"""公開SNSの集約と通知を一つのSQLite確定境界へ参加させる。"""
from __future__ import annotations

from typing import Any

from ai_rpg_world.application.common.aggregate_event_sink import CommandContextAggregateEventSink
from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.social.public_sns.command_repository import PublicSnsCommandRepositories
from ai_rpg_world.domain.sns.entity.notification import Notification
from ai_rpg_world.infrastructure.repository.scope_bound_repository import ScopeBoundRepository
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import SqlitePostRepository
from ai_rpg_world.infrastructure.repository.sqlite_public_sns_read_repository import SqlitePublicSnsReadRepository
from ai_rpg_world.infrastructure.repository.sqlite_reply_repository import SqliteReplyRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_notification_repository import SqliteSnsNotificationRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import SqliteSnsUserRepository
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import unwrap_transaction
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


class SqlitePublicSnsCommandRepositoryProvider:
    def __init__(self, unit_of_work: SqliteUnitOfWork, context: CommandContext[PublicSnsCommandRepositories]) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        self._connection = unit_of_work.connection
        sink = CommandContextAggregateEventSink(context, is_active=unit_of_work.is_in_transaction)
        def bind(cls: Any) -> Any:
            return ScopeBoundRepository(cls(self._connection, _commits_after_write=False,
                                           _initialize_schema=False, event_sink=sink), self._require_active)
        self.posts = bind(SqlitePostRepository)
        self.replies = bind(SqliteReplyRepository)
        self.users = bind(SqliteSnsUserRepository)
        self.notifications = bind(SqliteSnsNotificationRepository)
        self.read = ScopeBoundRepository(SqlitePublicSnsReadRepository(self._connection), self._require_active)

    def _require_active(self) -> None:
        if not self._context.is_open or not self._unit_of_work.is_in_transaction():
            raise CommandScopeStateException(current_state="closed", attempted_operation="use_scoped_repository")

    def notification_exists(self, source_event_id: str, recipient_token: str, kind: str) -> bool:
        self._require_active()
        return self._connection.execute(
            "SELECT 1 FROM game_sns_notifications WHERE source_event_id=? AND recipient_identity_token=? AND notification_type=? LIMIT 1",
            (source_event_id, recipient_token, kind),
        ).fetchone() is not None

    def pending_notifications(self, limit: int) -> list[Notification]:
        self._require_active()
        rows = self._connection.execute(
            "SELECT * FROM game_sns_notifications WHERE source_event_id IS NOT NULL AND observation_delivered=0 ORDER BY notification_id LIMIT ?",
            (limit,),
        ).fetchall()
        return [self.notifications._hydrate(row) for row in rows]


class SqlitePublicSnsCommandRepositoryProviderFactory:
    def create(self, context: CommandContext[PublicSnsCommandRepositories], transaction: TransactionPort) -> SqlitePublicSnsCommandRepositoryProvider:
        adapter = unwrap_transaction(transaction)
        if not isinstance(adapter, SqliteUnitOfWorkTransactionAdapter):
            raise TypeError("公開SNSにはSqliteUnitOfWorkTransactionAdapterが必要です")
        return SqlitePublicSnsCommandRepositoryProvider(adapter.unit_of_work, context)
