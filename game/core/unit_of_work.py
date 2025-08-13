from game.core.database import Database


class UnitOfWork:
    """
    トランザクション境界を提供する薄いユーティリティ。
    複数リポジトリが同一コネクションで1つのトランザクションに参加できるようにします。
    """

    def __init__(self, db: Database):
        self._db = db

    def transaction(self, mode: str = "IMMEDIATE"):
        """
        例:
            with uow.transaction("IMMEDIATE"):
                # 複数Repo呼び出しを原子的に実行
                pass
        """
        return self._db.transaction(mode)
