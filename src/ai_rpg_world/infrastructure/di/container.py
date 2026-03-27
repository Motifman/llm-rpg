"""
Dependency Injection Container - 依存性注入コンテナ実装

SNS 向けスタック（`get_unit_of_work_factory` / `get_unit_of_work_and_publisher`）は
`InMemoryUnitOfWork` + `InMemoryEventPublisherWithUow` に固定している。
`InMemoryEventPublisherWithUow` は SQLite UoW とそのままでは併用できない（イベント層の Option C）。
ゲーム DB 用の `SqliteUnitOfWorkFactory` が必要なときは `create_sqlite_unit_of_work_factory_for_game_db` を使い、
SNS コンテナの UoW ファクトリとは別経路で組み立てること。
"""
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, Tuple, Optional, Union

from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.infrastructure.unit_of_work.unit_of_work_factory_impl import InMemoryUnitOfWorkFactory
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWorkFactory
from ai_rpg_world.application.conversation.conversation_sqlite_wiring import (
    ConversationSqliteRepositories,
    attach_conversation_sqlite_repositories,
)
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
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_repository import InMemoryPlayerRepository
from ai_rpg_world.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from ai_rpg_world.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from ai_rpg_world.infrastructure.repository.in_memory_sns_notification_repository import InMemorySnsNotificationRepository
from ai_rpg_world.infrastructure.repository.in_memory_reply_repository import InMemoryReplyRepository
from ai_rpg_world.infrastructure.repository.sqlite_post_repository import SqlitePostRepository
from ai_rpg_world.infrastructure.repository.sqlite_reply_repository import SqliteReplyRepository
from ai_rpg_world.infrastructure.repository.sqlite_sns_notification_repository import (
    SqliteSnsNotificationRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_sns_user_repository import SqliteSnsUserRepository

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow


class DependencyInjectionContainer:
    """依存性注入コンテナ

    アプリケーション全体で使用する依存関係を管理します。
    SNS 用リポジトリは共有 `InMemoryDataStore` と In-Memory UoW に紐づく。
    """

    def __init__(self):
        """初期化"""
        self._data_store = InMemoryDataStore()
        self._unit_of_work_factory: Optional[UnitOfWorkFactory] = None
        self._event_publisher: Optional["InMemoryEventPublisherWithUow"] = None
        self._unit_of_work: Optional[InMemoryUnitOfWork] = None
        
        # リポジトリのキャッシュ
        self._player_repository: Optional[InMemoryPlayerRepository] = None
        self._post_repository: Optional[InMemoryPostRepository] = None
        self._user_repository: Optional[InMemorySnsUserRepository] = None
        self._notification_repository: Optional[InMemorySnsNotificationRepository] = None
        self._reply_repository: Optional[InMemoryReplyRepository] = None

    def get_unit_of_work_factory(self) -> UnitOfWorkFactory:
        """Unit of Workファクトリを取得"""
        if self._unit_of_work_factory is None:
            self._unit_of_work_factory = InMemoryUnitOfWorkFactory()
            self._init_uow_and_publisher()
            self._unit_of_work_factory._event_publisher = self._event_publisher
        return self._unit_of_work_factory

    def _init_uow_and_publisher(self):
        """UOWとパブリッシャーの初期化"""
        if self._unit_of_work is None:
            self._unit_of_work, self._event_publisher = InMemoryUnitOfWork.create_with_event_publisher()

    def get_unit_of_work_and_publisher(self) -> Tuple[InMemoryUnitOfWork, "InMemoryEventPublisherWithUow"]:
        """Unit of Workとイベントパブリッシャーのペアを取得"""
        self.get_unit_of_work_factory()
        return self._unit_of_work, self._event_publisher

    def get_data_store(self) -> InMemoryDataStore:
        """共有データストアを取得"""
        return self._data_store

    def get_player_repository(self) -> InMemoryPlayerRepository:
        """Playerリポジトリを取得"""
        if self._player_repository is None:
            uow, _ = self.get_unit_of_work_and_publisher()
            self._player_repository = InMemoryPlayerRepository(self._data_store, uow)
        return self._player_repository

    def get_post_repository(self) -> InMemoryPostRepository:
        """Postリポジトリを取得"""
        if self._post_repository is None:
            uow, _ = self.get_unit_of_work_and_publisher()
            self._post_repository = InMemoryPostRepository(self._data_store, uow)
        return self._post_repository

    def get_user_repository(self) -> InMemorySnsUserRepository:
        """Userリポジトリを取得"""
        if self._user_repository is None:
            uow, _ = self.get_unit_of_work_and_publisher()
            self._user_repository = InMemorySnsUserRepository(self._data_store, uow)
        return self._user_repository

    def get_notification_repository(self) -> InMemorySnsNotificationRepository:
        """Notificationリポジトリを取得"""
        if self._notification_repository is None:
            uow, _ = self.get_unit_of_work_and_publisher()
            self._notification_repository = InMemorySnsNotificationRepository(self._data_store, uow)
        return self._notification_repository

    def get_reply_repository(self) -> InMemoryReplyRepository:
        """Replyリポジトリを取得"""
        if self._reply_repository is None:
            uow, _ = self.get_unit_of_work_and_publisher()
            self._reply_repository = InMemoryReplyRepository(self._data_store, uow)
        return self._reply_repository

    @staticmethod
    def create_sqlite_unit_of_work_factory_for_game_db(
        database: Union[str, Path],
    ) -> SqliteUnitOfWorkFactory:
        """ゲーム永続化用の `SqliteUnitOfWorkFactory` を返す（SNS 用 `get_unit_of_work_factory` とは別）。

        `InMemoryEventPublisherWithUow` と同一プロセスで使い回さないこと。
        """
        return SqliteUnitOfWorkFactory(database)


class SqliteSocialDependencyInjectionContainer:
    """SNS 用 SQLite コンテナ。

    既存の `DependencyInjectionContainer` を壊さず、本番経路で InMemory に固定しないための
    明示的な SQLite 版コンテナを提供する。
    """

    def __init__(self, database: Union[str, Path]):
        self._database = Path(database)
        self._connection: Optional[sqlite3.Connection] = None
        self._unit_of_work_factory: Optional[SqliteUnitOfWorkFactory] = None
        self._user_repository: Optional[SqliteSnsUserRepository] = None
        self._post_repository: Optional[SqlitePostRepository] = None
        self._notification_repository: Optional[SqliteSnsNotificationRepository] = None
        self._reply_repository: Optional[SqliteReplyRepository] = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            connection = sqlite3.connect(str(self._database))
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

    def __init__(self, database: Union[str, Path]):
        self._database = Path(database)
        self._connection: Optional[sqlite3.Connection] = None
        self._unit_of_work_factory: Optional[SqliteUnitOfWorkFactory] = None
        self._world_state: Optional[WorldStateSqliteRepositories] = None
        self._static_master: Optional[StaticMasterSqliteRepositories] = None
        self._shop: Optional[ShopSqliteRepositories] = None
        self._guild: Optional[GuildSqliteRepositories] = None
        self._quest: Optional[QuestSqliteRepositories] = None
        self._skill: Optional[SkillSqliteRepositories] = None
        self._conversation: Optional[ConversationSqliteRepositories] = None
        self._social: Optional[SocialSqliteRepositories] = None
        self._trade_command_repositories: Optional[tuple] = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            connection = sqlite3.connect(str(self._database))
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

    def get_conversation_repositories(self) -> ConversationSqliteRepositories:
        if self._conversation is None:
            self._conversation = attach_conversation_sqlite_repositories(
                self._get_connection()
            )
        return self._conversation

    def get_social_repositories(self) -> SocialSqliteRepositories:
        if self._social is None:
            self._social = attach_social_sqlite_repositories(self._get_connection())
        return self._social

    def get_trade_command_repositories(self) -> tuple:
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
    "DependencyInjectionContainer",
    "SqliteGameDependencyInjectionContainer",
    "SqliteSocialDependencyInjectionContainer",
]
