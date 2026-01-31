"""
Dependency Injection Container - 依存性注入コンテナ実装
"""
from typing import TYPE_CHECKING, Tuple, Optional

from src.domain.common.unit_of_work_factory import UnitOfWorkFactory
from src.infrastructure.unit_of_work.unit_of_work_factory_impl import InMemoryUnitOfWorkFactory
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from src.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from src.infrastructure.repository.in_memory_player_repository import InMemoryPlayerRepository
from src.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.infrastructure.repository.in_memory_sns_notification_repository import InMemorySnsNotificationRepository
from src.infrastructure.repository.in_memory_reply_repository import InMemoryReplyRepository

if TYPE_CHECKING:
    from src.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow


class DependencyInjectionContainer:
    """依存性注入コンテナ
    
    アプリケーション全体で使用する依存関係を管理します。
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
            factory_func = self._unit_of_work_factory.create if self._unit_of_work_factory else None
            self._unit_of_work, self._event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
                unit_of_work_factory=factory_func
            )

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
