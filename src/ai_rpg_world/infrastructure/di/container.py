"""ゲームと公開 SNS の SQLite リポジトリを組み立てる。"""
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from ai_rpg_world.application.guild.guild_sqlite_wiring import (
    GuildSqliteRepositories,
    attach_guild_sqlite_repositories,
)
from ai_rpg_world.application.quest.quest_sqlite_wiring import (
    QuestSqliteRepositories,
    attach_quest_sqlite_repositories,
)
from ai_rpg_world.application.shop.shop_sqlite_wiring import (
    ShopSqliteRepositories,
    attach_shop_sqlite_repositories,
)
from ai_rpg_world.application.skill.skill_sqlite_wiring import (
    SkillSqliteRepositories,
    attach_skill_sqlite_repositories,
)
from ai_rpg_world.application.social.social_sqlite_wiring import (
    SocialSqliteRepositories,
    attach_social_sqlite_repositories,
    bootstrap_social_schema,
)
from ai_rpg_world.application.static_master_sqlite_wiring import (
    StaticMasterSqliteRepositories,
    attach_static_master_sqlite_repositories,
)
from ai_rpg_world.application.trade.trade_command_sqlite_wiring import (
    attach_trade_command_sqlite_repositories,
)
from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    WorldStateSqliteRepositories,
    attach_world_state_sqlite_repositories,
)
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import SqlitePostRepository
from ai_rpg_world.infrastructure.repository.sqlite_reply_repository import SqliteReplyRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_notification_repository import (
    SqliteSnsNotificationRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import SqliteSnsUserRepository
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWorkFactory

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import SqliteItemWriteRepository
    from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
        SqlitePlayerInventoryWriteRepository,
    )
    from ai_rpg_world.infrastructure.repository.sqlite_player_profile_write_repository import (
        SqlitePlayerProfileWriteRepository,
    )
    from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
        SqlitePlayerStatusWriteRepository,
    )
    from ai_rpg_world.infrastructure.repository.sqlite_trade_aggregate_repository import SqliteTradeAggregateRepository


TradeCommandRepositories = tuple[
    "SqliteTradeAggregateRepository",
    "SqlitePlayerInventoryWriteRepository",
    "SqlitePlayerStatusWriteRepository",
    "SqlitePlayerProfileWriteRepository",
    "SqliteItemWriteRepository",
]


class SqliteSocialDependencyInjectionContainer:
    """SNS 用 SQLite コンテナ。

    公開 SNS のデータを SQLite に保存するためのリポジトリを提供する。
    """

    def __init__(self, database: str | Path):
        self._database = Path(database)
        self._connection: sqlite3.Connection | None = None
        self._unit_of_work_factory: SqliteUnitOfWorkFactory | None = None
        self._user_repository: SqliteSnsUserRepository | None = None
        self._post_repository: SqlitePostRepository | None = None
        self._notification_repository: SqliteSnsNotificationRepository | None = None
        self._reply_repository: SqliteReplyRepository | None = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            connection = sqlite3.connect(
                str(self._database),
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            bootstrap_social_schema(connection)
            self._connection = connection
        return self._connection

    def get_unit_of_work_factory(self) -> SqliteUnitOfWorkFactory:
        if self._unit_of_work_factory is None:
            self._unit_of_work_factory = SqliteUnitOfWorkFactory(self._database)
        return self._unit_of_work_factory

    def get_user_repository(self) -> SqliteSnsUserRepository:
        if self._user_repository is None:
            self._user_repository = SqliteSnsUserRepository.for_standalone_connection(
                self._get_connection()
            )
        return self._user_repository

    def get_post_repository(self) -> SqlitePostRepository:
        if self._post_repository is None:
            self._post_repository = SqlitePostRepository.for_standalone_connection(
                self._get_connection()
            )
        return self._post_repository

    def get_notification_repository(self) -> SqliteSnsNotificationRepository:
        if self._notification_repository is None:
            self._notification_repository = (
                SqliteSnsNotificationRepository.for_standalone_connection(
                    self._get_connection()
                )
            )
        return self._notification_repository

    def get_reply_repository(self) -> SqliteReplyRepository:
        if self._reply_repository is None:
            self._reply_repository = SqliteReplyRepository.for_standalone_connection(
                self._get_connection()
            )
        return self._reply_repository

    def close(self) -> None:
        if self._connection is None:
            return
        self._connection.close()
        self._connection = None


class SqliteGameDependencyInjectionContainer:
    """単一 game DB を正式入口にする SQLite コンテナ。"""

    def __init__(self, database: str | Path):
        self._database = Path(database)
        self._connection: sqlite3.Connection | None = None
        self._unit_of_work_factory: SqliteUnitOfWorkFactory | None = None
        self._world_state: WorldStateSqliteRepositories | None = None
        self._static_master: StaticMasterSqliteRepositories | None = None
        self._shop: ShopSqliteRepositories | None = None
        self._guild: GuildSqliteRepositories | None = None
        self._quest: QuestSqliteRepositories | None = None
        self._skill: SkillSqliteRepositories | None = None
        self._social: SocialSqliteRepositories | None = None
        self._trade_command_repositories: TradeCommandRepositories | None = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            connection = sqlite3.connect(
                str(self._database),
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            bootstrap_social_schema(connection)
            self._connection = connection
        return self._connection

    def get_unit_of_work_factory(self) -> SqliteUnitOfWorkFactory:
        if self._unit_of_work_factory is None:
            self._unit_of_work_factory = SqliteUnitOfWorkFactory(self._database)
        return self._unit_of_work_factory

    def get_world_state_repositories(self) -> WorldStateSqliteRepositories:
        if self._world_state is None:
            self._world_state = attach_world_state_sqlite_repositories(
                self._get_connection()
            )
        return self._world_state

    def get_static_master_repositories(self) -> StaticMasterSqliteRepositories:
        if self._static_master is None:
            self._static_master = attach_static_master_sqlite_repositories(
                self._get_connection()
            )
        return self._static_master

    def get_shop_repositories(self) -> ShopSqliteRepositories:
        if self._shop is None:
            self._shop = attach_shop_sqlite_repositories(self._get_connection())
        return self._shop

    def get_guild_repositories(self) -> GuildSqliteRepositories:
        if self._guild is None:
            self._guild = attach_guild_sqlite_repositories(self._get_connection())
        return self._guild

    def get_quest_repositories(self) -> QuestSqliteRepositories:
        if self._quest is None:
            self._quest = attach_quest_sqlite_repositories(self._get_connection())
        return self._quest

    def get_skill_repositories(self) -> SkillSqliteRepositories:
        if self._skill is None:
            self._skill = attach_skill_sqlite_repositories(self._get_connection())
        return self._skill

    def get_social_repositories(self) -> SocialSqliteRepositories:
        if self._social is None:
            self._social = attach_social_sqlite_repositories(self._get_connection())
        return self._social

    def get_trade_command_repositories(self) -> TradeCommandRepositories:
        if self._trade_command_repositories is None:
            self._trade_command_repositories = attach_trade_command_sqlite_repositories(
                self._get_connection()
            )
        return self._trade_command_repositories

    def close(self) -> None:
        if self._connection is None:
            return
        self._connection.close()
        self._connection = None


__all__ = [
    "SqliteGameDependencyInjectionContainer",
    "SqliteSocialDependencyInjectionContainer",
]
