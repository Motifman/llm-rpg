"""outbox worker向けSQLite pending取得と試行結果の永続化。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable, Union

from ai_rpg_world.application.common.outbox_worker import (
    OutboxFailureDisposition,
    OutboxRetryPolicy,
    StoredOutboxMessage,
)


class SqliteOutboxDeliveryStore:
    """1つのworkerがpending行を登録順で処理するSQLite adapter。"""

    def __init__(
        self,
        database: Union[str, Path],
        *,
        retry_policy: OutboxRetryPolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if str(database) == ":memory:":
            raise ValueError("SQLite outbox workerには共有可能なファイルDBが必要です")
        self._database = str(Path(database).expanduser().resolve())
        self._retry_policy = retry_policy or OutboxRetryPolicy()
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def fetch_pending(self, *, limit: int) -> tuple[StoredOutboxMessage, ...]:
        """未配送行をoutbox登録順で最大limit件返す。"""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limitは1以上の整数である必要があります")
        connection = sqlite3.connect(self._database)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT event_id, event_type, payload, payload_schema_version,
                       next_attempt_at
                FROM command_event_outbox
                WHERE status = 'pending'
                ORDER BY outbox_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            now = self._now()
            ready_rows: list[sqlite3.Row] = []
            for row in rows:
                raw_next_attempt = row["next_attempt_at"]
                if raw_next_attempt is not None:
                    next_attempt_at = datetime.fromisoformat(str(raw_next_attempt))
                    if (
                        next_attempt_at.tzinfo is None
                        or next_attempt_at.utcoffset() is None
                    ):
                        raise RuntimeError(
                            "outboxのnext_attempt_atにタイムゾーンがありません: "
                            f"event_id={row['event_id']}"
                        )
                    if next_attempt_at > now:
                        break
                ready_rows.append(row)
            return tuple(
                StoredOutboxMessage(
                    event_id=str(row["event_id"]),
                    event_type=str(row["event_type"]),
                    payload=bytes(row["payload"]),
                    payload_schema_version=int(row["payload_schema_version"]),
                )
                for row in ready_rows
            )
        finally:
            connection.close()

    def mark_delivered(self, event_id: str) -> None:
        """handler成功後に1行だけ配達済みへ変更する。"""
        self._record_attempt(event_id, status="delivered", error=None)

    def record_retryable_failure(
        self, event_id: str, error: Exception
    ) -> OutboxFailureDisposition:
        """一時失敗の次回時刻、または試行上限による隔離を確定する。"""
        now = self._now()
        connection = sqlite3.connect(self._database)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT attempt_count
                FROM command_event_outbox
                WHERE event_id = ? AND status = 'pending'
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(
                    "更新対象のpending outbox行が一意に存在しません: "
                    f"event_id={event_id}"
                )
            attempt_count = int(row["attempt_count"]) + 1
            dead_lettered = attempt_count >= self._retry_policy.max_attempts
            next_attempt_at = (
                None
                if dead_lettered
                else now + self._retry_policy.delay_after(attempt_count)
            )
            status = "dead_letter" if dead_lettered else "pending"
            cursor = connection.execute(
                """
                UPDATE command_event_outbox
                SET status = ?,
                    attempt_count = ?,
                    last_attempted_at = ?,
                    last_error = ?,
                    next_attempt_at = ?,
                    dead_lettered_at = ?
                WHERE event_id = ? AND status = 'pending'
                """,
                (
                    status,
                    attempt_count,
                    now.isoformat(),
                    self._error_text(error),
                    None if next_attempt_at is None else next_attempt_at.isoformat(),
                    now.isoformat() if dead_lettered else None,
                    event_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "更新対象のpending outbox行が一意に存在しません: "
                    f"event_id={event_id}"
                )
            connection.commit()
            return OutboxFailureDisposition(
                attempt_count=attempt_count,
                next_attempt_at=next_attempt_at,
                dead_lettered=dead_lettered,
            )
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

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
        attempted_at = self._now().isoformat()
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
                    rejected_at = ?,
                    next_attempt_at = NULL
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

    def _now(self) -> datetime:
        now = self._now_provider()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise ValueError("now_providerはタイムゾーン付き日時を返す必要があります")
        return now


__all__ = ["SqliteOutboxDeliveryStore"]
