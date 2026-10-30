"""公開SNSの確定境界と確定後配送を、一箇所で組み立てる。"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from ai_rpg_world.application.common.command_scope import RepositoryProviderFactoryPort
from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory, TransactionFactoryPort
from ai_rpg_world.application.social.public_sns.command_repository import PublicSnsCommandRepositories
from ai_rpg_world.application.social.public_sns.command_service import PublicSnsCommandService
from ai_rpg_world.application.social.public_sns.notification_delivery import (
    NotificationDelivery,
    PublicSnsAfterCommitHandoff,
    PublicSnsIncomingNotificationService,
)
from ai_rpg_world.application.social.public_sns.notification_dispatcher import PublicSnsNotificationDispatcher
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_public_sns_command_repository_provider import (
    InMemoryPublicSnsCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.sqlite_public_sns_command_repository_provider import (
    SqlitePublicSnsCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
    SqliteUnitOfWorkTransactionFactory,
)


def _build(
    transaction_factory: TransactionFactoryPort,
    repositories: RepositoryProviderFactoryPort[PublicSnsCommandRepositories],
    deliver_notification: NotificationDelivery | None,
) -> PublicSnsCommandService:
    handoff = PublicSnsAfterCommitHandoff(deliver_notification)
    scope_factory = CommandScopeFactory(
        transaction_factory,
        repository_provider_factory=repositories,
        sync_dispatcher=PublicSnsNotificationDispatcher(),
        after_commit_handoff=handoff,
    )
    handoff.bind_scope_factory(scope_factory)
    return PublicSnsCommandService(scope_factory, notification_handoff=handoff)


def create_in_memory_public_sns_command_service(
    data_store: InMemoryDataStore,
    *,
    deliver_notification: NotificationDelivery | None = None,
) -> PublicSnsCommandService:
    return _build(
        InMemoryUnitOfWorkTransactionFactory(data_store),
        cast(
            RepositoryProviderFactoryPort[PublicSnsCommandRepositories],
            InMemoryPublicSnsCommandRepositoryProviderFactory(),
        ),
        deliver_notification,
    )


def create_sqlite_public_sns_command_service(
    database: str | Path,
    *,
    deliver_notification: NotificationDelivery | None = None,
) -> PublicSnsCommandService:
    # schemaはここで初期化済みであること。providerは操作中のDDLを行わない。
    return _build(
        SqliteUnitOfWorkTransactionFactory(database),
        cast(
            RepositoryProviderFactoryPort[PublicSnsCommandRepositories],
            SqlitePublicSnsCommandRepositoryProviderFactory(),
        ),
        deliver_notification,
    )
