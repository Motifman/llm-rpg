"""取引read model投影をconsumer inbox付きで一度だけ実行するadapter。"""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Union

from ai_rpg_world.application.trade.handlers.trade_projection_executor import (
    TradeProjection,
    validate_consumer_identity,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_read_model_repository import (
    SqliteTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.trade_read_model_sqlite import (
    init_trade_read_model_schema,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteUnitOfWork,
)


class InMemoryTradeProjectionExecutor:
    """単一プロセス内で取引投影の重複実行を防ぐ。"""

    def __init__(self, repository: InMemoryTradeReadModelRepository) -> None:
        self._repository = repository
        self._processed: set[tuple[str, int]] = set()
        self._lock = RLock()

    def execute_once(
        self,
        *,
        consumer_id: str,
        event_id: int,
        projection: TradeProjection,
    ) -> bool:
        """同じconsumerとeventの組をプロセス内で一度だけ投影する。"""
        validate_consumer_identity(consumer_id=consumer_id, event_id=event_id)
        key = (consumer_id, event_id)
        with self._lock:
            if key in self._processed:
                return False
            snapshot = self._repository.take_transaction_snapshot()
            try:
                projection(self._repository)
            except BaseException:
                self._repository.restore_transaction_snapshot(snapshot)
                raise
            self._processed.add(key)
            return True


class SqliteTradeProjectionExecutor:
    """投影更新とconsumer inbox行を同じSQLite transactionで確定する。"""

    def __init__(self, database: Union[str, Path]) -> None:
        if str(database) == ":memory:":
            raise ValueError("SQLite取引投影には共有可能なファイルDBが必要です")
        self._database = str(Path(database).expanduser().resolve())
        uow = SqliteUnitOfWork(self._database)
        with uow:
            init_trade_read_model_schema(uow.connection)

    def execute_once(
        self,
        *,
        consumer_id: str,
        event_id: int,
        projection: TradeProjection,
    ) -> bool:
        """inbox取得に成功したeventだけを共有repositoryへ投影する。"""
        validate_consumer_identity(consumer_id=consumer_id, event_id=event_id)
        uow = SqliteUnitOfWork(self._database)
        with uow:
            connection = uow.connection
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO event_consumer_inbox (
                    consumer_id, event_id, processed_at
                ) VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (consumer_id, str(event_id)),
            )
            if cursor.rowcount == 0:
                return False
            repository = SqliteTradeReadModelRepository.for_shared_unit_of_work(
                connection
            )
            projection(repository)
            return True


__all__ = ["InMemoryTradeProjectionExecutor", "SqliteTradeProjectionExecutor"]
