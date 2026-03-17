"""
Unit of Workインターフェース
DDDにおけるトランザクション管理の抽象化を提供します。
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Protocol, Tuple

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.domain_event import BaseDomainEvent


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
    def add_events(self, events: list) -> None:
        """保留中のイベントを追加"""
        pass

    @abstractmethod
    def add_events_from_aggregate(self, aggregate: any) -> None:
        """集約からイベントを収集し、add_events 経由で追加する（イベント収集 1 本化）"""
        pass

    def get_sync_processed_count(self) -> int:
        """同期イベント処理済み件数を返す。flush_sync_events の複数回呼び出しで重複処理を防ぐ。"""
        ...

    def get_pending_events_since(self, processed_count: int) -> Tuple[List["BaseDomainEvent"], int]:
        """processed_count 以降の保留イベントを取得する。戻り値は (イベントリスト, 次の processed_count)。"""
        ...

    def advance_sync_processed_count(self, new_count: int) -> None:
        """同期イベント処理済み件数を進める。"""
        ...

    @abstractmethod
    def __enter__(self):
        """コンテキストマネージャー開始"""
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー終了"""
        pass
