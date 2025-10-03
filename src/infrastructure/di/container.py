"""
Dependency Injection Container - 依存性注入コンテナ実装
"""
from typing import TYPE_CHECKING, Tuple, Optional

from src.domain.common.unit_of_work_factory import UnitOfWorkFactory
from src.infrastructure.unit_of_work.unit_of_work_factory_impl import InMemoryUnitOfWorkFactory
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from src.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow


class DependencyInjectionContainer:
    """依存性注入コンテナ

    アプリケーション全体で使用する依存関係を管理し、
    Unit of Workファクトリなどのインスタンスを提供します。
    """

    def __init__(self):
        """初期化"""
        self._unit_of_work_factory: Optional[UnitOfWorkFactory] = None
        self._event_publisher: Optional["InMemoryEventPublisherWithUow"] = None
        self._unit_of_work: Optional[InMemoryUnitOfWork] = None

    def get_unit_of_work_factory(self) -> UnitOfWorkFactory:
        """Unit of Workファクトリを取得

        必要に応じてUnit of Workとイベントパブリッシャーを作成し、
        適切な依存関係を設定します。

        Returns:
            UnitOfWorkFactory: Unit of Workファクトリインスタンス
        """
        if self._unit_of_work_factory is None:
            # まずファクトリを作成（空のイベントパブリッシャーで）
            self._unit_of_work_factory = InMemoryUnitOfWorkFactory()

            # Unit of Workとイベントパブリッシャーを作成
            self._unit_of_work, self._event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
                unit_of_work_factory=self._unit_of_work_factory.create
            )

            # ファクトリにイベントパブリッシャーを設定
            self._unit_of_work_factory._event_publisher = self._event_publisher

        return self._unit_of_work_factory

    def get_unit_of_work_and_publisher(self) -> Tuple[InMemoryUnitOfWork, "InMemoryEventPublisherWithUow"]:
        """Unit of Workとイベントパブリッシャーのペアを取得

        Returns:
            Tuple[InMemoryUnitOfWork, InMemoryEventPublisherWithUow]:
                Unit of Workとイベントパブリッシャーのタプル
        """
        # ファクトリを取得することで初期化を保証
        self.get_unit_of_work_factory()

        if self._unit_of_work is None or self._event_publisher is None:
            raise RuntimeError("Unit of Work and Event Publisher not initialized")

        return self._unit_of_work, self._event_publisher
