"""
Unit of Workインターフェース
DDDにおけるトランザクション管理の抽象化を提供します。
"""
from abc import abstractmethod
from collections.abc import Sequence
from types import TracebackType
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.domain_event import DomainEvent


class UnitOfWork(Protocol):
    """Unit of Workインターフェース"""

    @abstractmethod
    def begin(self) -> None:
        """トランザクション開始"""
        pass

    @abstractmethod
    def commit(self) -> None:
        """コミット"""
        pass

    @abstractmethod
    def rollback(self) -> None:
        """ロールバック"""
        pass

    @abstractmethod
    def add_events(self, events: Sequence["DomainEvent"]) -> None:
        """保留中のイベントを追加"""
        pass

    @abstractmethod
    def add_events_from_aggregate(self, aggregate: Any) -> None:
        """集約からイベントを収集し、add_events 経由で追加する（イベント収集 1 本化）"""
        pass

    def get_committed_events(self) -> list["DomainEvent"]:
        """コミット成功後に取り出し可能なイベントを返す。post-commit orchestration で使用。"""
        ...

    def clear_committed_events(self) -> None:
        """コミット済みイベントをクリアする。post-commit orchestration 完了後に呼ぶ。"""
        ...

    @abstractmethod
    def __enter__(self) -> "UnitOfWork":
        """コンテキストマネージャー開始"""
        pass

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """コンテキストマネージャー終了"""
        pass
