"""outbox worker向けSQLite pending取得と試行結果の永続化。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Union

from ai_rpg_world.application.common.outbox_worker import StoredOutboxMessage


class SqliteOutboxDeliveryStore:
    """1つのworkerがpending行を登録順で処理するSQLite adapter。"""

    def __init__(self, database: Union[str, Path]) -> None:
        if str(database) == ":memory:":
            raise ValueError("SQLite outbox workerには共有可能なファイルDBが必要です")
        self._database = str(Path(database).expanduser().resolve())

    def fetch_pending(self, *, limit: int) -> tuple[StoredOutboxMessage, ...]:
        """未配送行をoutbox登録順で最大limit件返す。"""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limitは1以上の整数である必要があります")
        connection = sqlite3.connect(self._database)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT event_id, event_type, payload, payload_schema_version
                FROM command_event_outbox
                WHERE status = 'pending'
                ORDER BY outbox_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return tuple(
                StoredOutboxMessage(
                    event_id=str(row["event_id"]),
                    event_type=str(row["event_type"]),
                    payload=bytes(row["payload"]),
                    payload_schema_version=int(row["payload_schema_version"]),
                )
                for row in rows
            )
        finally:
            connection.close()

    def mark_delivered(self, event_id: str) -> None:
        """handler成功後に1行だけ配達済みへ変更する。"""
        self._record_attempt(event_id, status="delivered", error=None)

    def record_retryable_failure(self, event_id: str, error: Exception) -> None:
        """一時失敗の試行情報を残し、statusはpendingを維持する。"""
        self._record_attempt(event_id, status="pending", error=error)

    def mark_rejected(self, event_id: str, error: Exception) -> None:
        """復元不能行を通常再試行から隔離する。"""
        self._record_attempt(event_id, status="rejected", error=error)

    def _record_attempt(
        self,
        event_id: str,
        *,
        status: str,
        error: Exception | None,
    ) -> None:
        attempted_at = datetime.now(timezone.utc).isoformat()
        last_error = None if error is None else self._error_text(error)
        delivered_at = attempted_at if status == "delivered" else None
        rejected_at = attempted_at if status == "rejected" else None
        connection = sqlite3.connect(self._database)
        try:
            cursor = connection.execute(
                """
                UPDATE command_event_outbox
                SET status = ?,
                    delivered_at = ?,
                    attempt_count = attempt_count + 1,
                    last_attempted_at = ?,
                    last_error = ?,
                    rejected_at = ?
                WHERE event_id = ? AND status = 'pending'
                """,
                (
                    status,
                    delivered_at,
                    attempted_at,
                    last_error,
                    rejected_at,
                    event_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "更新対象のpending outbox行が一意に存在しません: "
                    f"event_id={event_id}"
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _error_text(error: Exception) -> str:
        return f"{type(error).__name__}: {error}"[:2000]


__all__ = ["SqliteOutboxDeliveryStore"]
