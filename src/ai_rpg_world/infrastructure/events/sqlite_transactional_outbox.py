"""SQLite transactionと同時に確定するドメインイベントoutbox。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable, Sequence, Union

from ai_rpg_world.application.common.command_scope import TransactionPort
from ai_rpg_world.application.common.transactional_outbox import StagedOutboxBatch
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_payload_serializer import EventPayloadSerializer
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    unwrap_transaction,
)


class SqliteTransactionalOutbox:
    """再送対象イベントを業務状態と同じSQLite transactionへ保存する。"""

    def __init__(
        self,
        database: Union[str, Path],
        *,
        serializer: EventPayloadSerializer,
        is_durable: Callable[[DomainEvent], bool],
    ) -> None:
        if str(database) == ":memory:":
            raise ValueError("SQLite outboxには共有可能なファイルDBが必要です")
        schema_version = serializer.schema_version
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version < 1
        ):
            raise ValueError("serializer.schema_versionは1以上の整数が必要です")
        if not callable(is_durable):
            raise TypeError("is_durableは呼出し可能である必要があります")
        self._database_path = Path(database).expanduser().resolve()
        self._database = str(self._database_path)
        self._serializer = serializer
        self._payload_schema_version = schema_version
        self._is_durable = is_durable

    def stage(
        self,
        events: Sequence[DomainEvent],
        transaction: TransactionPort,
    ) -> StagedOutboxBatch:
        """再送対象を現在のSQLite transactionへ重複なく登録する。"""
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, SqliteUnitOfWorkTransactionAdapter):
            raise TypeError(
                "SqliteTransactionalOutboxには"
                "SqliteUnitOfWorkTransactionAdapterが必要です"
            )
        if base_transaction.unit_of_work.database_path != self._database_path:
            raise ValueError(
                "SQLite outboxとtransactionは同じDBパスを共有する必要があります"
            )
        connection = base_transaction.unit_of_work.connection
        staged_ids: list[str] = []
        for event in events:
            if not self._is_durable(event):
                continue
            event_id = str(event.event_id)
            payload = self._serializer.serialize(event)
            event_type = f"{type(event).__module__}:{type(event).__qualname__}"
            connection.execute(
                """
                INSERT OR IGNORE INTO command_event_outbox (
                    event_id, event_type, payload, payload_schema_version,
                    status, created_at, delivered_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, NULL)
                """,
                (
                    event_id,
                    event_type,
                    payload,
                    self._payload_schema_version,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT event_type, payload FROM command_event_outbox WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None or str(row[0]) != event_type or bytes(row[1]) != payload:
                raise RuntimeError(
                    "同じevent_idに異なるoutbox payloadが保存されています: "
                    f"event_id={event_id}"
                )
            staged_ids.append(event_id)
        return StagedOutboxBatch(event_ids=tuple(dict.fromkeys(staged_ids)))

    def mark_delivered(self, batch: StagedOutboxBatch) -> None:
        """即時handoffに成功した行を別transactionで配達済みにする。"""
        if not batch.event_ids:
            return
        connection = sqlite3.connect(self._database)
        try:
            placeholders = ",".join("?" for _ in batch.event_ids)
            existing = connection.execute(
                f"SELECT COUNT(*) FROM command_event_outbox "
                f"WHERE event_id IN ({placeholders})",
                batch.event_ids,
            ).fetchone()
            if existing is None or int(existing[0]) != len(batch.event_ids):
                raise RuntimeError("配達済みにするoutbox行が見つかりません")
            connection.execute(
                f"UPDATE command_event_outbox "
                f"SET status = 'delivered', delivered_at = ? "
                f"WHERE event_id IN ({placeholders})",
                (datetime.now(timezone.utc).isoformat(), *batch.event_ids),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["SqliteTransactionalOutbox"]
