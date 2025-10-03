"""
Unit of Work Factory Implementation - Unit of Workファクトリの具体実装
"""
from typing import Optional, TYPE_CHECKING
from src.domain.common.unit_of_work import UnitOfWork
from src.domain.common.unit_of_work_factory import UnitOfWorkFactory
from .in_memory_unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from src.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow


class InMemoryUnitOfWorkFactory(UnitOfWorkFactory):
    """インメモリUnit of Workファクトリ実装

    イベントパブリッシャーと連携し、循環参照を避けたUnit of Work作成を提供します。
    """

    def __init__(self, event_publisher: Optional["InMemoryEventPublisherWithUow"] = None):
        """初期化

        Args:
            event_publisher: 関連付けるイベントパブリッシャー（任意）
        """
        self._event_publisher = event_publisher
        self._factory_function: Optional[callable] = None

    def create(self) -> UnitOfWork:
        """Unit of Workインスタンスを作成

        初回呼び出し時にファクトリ関数を作成し、
        以後は同じファクトリ関数を使用してインスタンスを作成します。

        Returns:
            UnitOfWork: 新しいUnit of Workインスタンス
        """
        if self._factory_function is None:
            # 初回のみファクトリ関数を作成（循環参照を避ける）
            self._factory_function = lambda: InMemoryUnitOfWork(
                event_publisher=self._event_publisher,
                unit_of_work_factory=self.create
            )

        return self._factory_function()
