"""
Unit of Work Factory - Unit of Workインスタンス作成の抽象化
"""
from typing import Protocol
from .unit_of_work import UnitOfWork


class UnitOfWorkFactory(Protocol):
    """Unit of Workファクトリインターフェース

    Unit of Workインスタンスの作成を抽象化し、
    イベントハンドラなどの別トランザクション処理で使用されます。
    """

    def create(self) -> UnitOfWork:
        """Unit of Workインスタンスを作成

        Returns:
            UnitOfWork: 新しいUnit of Workインスタンス
        """
        ...
