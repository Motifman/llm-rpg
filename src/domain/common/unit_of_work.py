"""
Unit of Workインターフェース
DDDにおけるトランザクション管理の抽象化を提供します。
"""
from abc import ABC, abstractmethod
from typing import Protocol


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
    def __enter__(self):
        """コンテキストマネージャー開始"""
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー終了"""
        pass
