"""想起後再解釈の SQLite ストア。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    EpisodicRecallObservation,
    EpisodicReinterpretationEntry,
    EpisodicReinterpretationStatus,
    IEpisodicRecallBufferStore,
    IEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)

_SCHEMA_NAMESPACE = "episodic-reinterpretation-mvp-v1"


def _dt_to_text(dt: datetime) -> str:
    return dt.isoformat()


def _text_to_dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _dt_key(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.timestamp()


def _recall_to_payload(row: EpisodicRecallObservation) -> dict[str, Any]:
    return {
        "recall_id": row.recall_id,
        "player_id": row.player_id,
        "episode_id": row.episode_id,
        "recalled_at": _dt_to_text(row.recalled_at),
        "source_axes": list(row.source_axes),
        "current_state_snapshot": row.current_state_snapshot,
        "recent_events_snapshot": row.recent_events_snapshot,
        "persona_snapshot": row.persona_snapshot,
        "situation_cues": list(row.situation_cues),
        "turn_index": row.turn_index,
    }


def _payload_to_recall(data: dict[str, Any]) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=str(data["recall_id"]),
        player_id=int(data["player_id"]),
        episode_id=str(data["episode_id"]),
        recalled_at=_text_to_dt(str(data["recalled_at"])),
        source_axes=tuple(str(x) for x in data.get("source_axes", ())),
        current_state_snapshot=str(data.get("current_state_snapshot", "")),
        recent_events_snapshot=str(data.get("recent_events_snapshot", "")),
        persona_snapshot=str(data.get("persona_snapshot", "")),
        situation_cues=tuple(str(x) for x in data.get("situation_cues", ())),
        turn_index=int(data.get("turn_index", 0)),
    )


def _entry_to_payload(entry: EpisodicReinterpretationEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "player_id": entry.player_id,
        "episode_id": entry.episode_id,
        "created_at": _dt_to_text(entry.created_at),
        "turn_index": entry.turn_index,
        "current_interpretation": entry.current_interpretation,
        "current_recall_text": entry.current_recall_text,
        "source_recall_ids": list(entry.source_recall_ids),
        "status": entry.status.value,
        "superseded_at": _dt_to_text(entry.superseded_at) if entry.superseded_at else None,
    }


def _payload_to_entry(data: dict[str, Any]) -> EpisodicReinterpretationEntry:
    superseded_raw = data.get("superseded_at")
    return EpisodicReinterpretationEntry(
        entry_id=str(data["entry_id"]),
        player_id=int(data["player_id"]),
        episode_id=str(data["episode_id"]),
        created_at=_text_to_dt(str(data["created_at"])),
        turn_index=int(data["turn_index"]),
        current_interpretation=str(data["current_interpretation"]),
        current_recall_text=str(data["current_recall_text"]),
        source_recall_ids=tuple(str(x) for x in data.get("source_recall_ids", ())),
        status=EpisodicReinterpretationStatus(str(data["status"])),
        superseded_at=_text_to_dt(str(superseded_raw)) if superseded_raw else None,
    )


def _init_schema_v1(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE episodic_recall_observations (
            player_id INTEGER NOT NULL,
            recall_id TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            recalled_at_key REAL NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (player_id, recall_id)
        );
        CREATE INDEX idx_episodic_recall_observations_pending
            ON episodic_recall_observations (player_id, recalled_at_key ASC, recall_id ASC);

        CREATE TABLE episodic_reinterpretation_journal (
            player_id INTEGER NOT NULL,
            entry_id TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            created_at_key REAL NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (player_id, entry_id)
        );
        CREATE INDEX idx_episodic_reinterpretation_active
            ON episodic_reinterpretation_journal (player_id, episode_id, status);
        CREATE INDEX idx_episodic_reinterpretation_episode_time
            ON episodic_reinterpretation_journal
                (player_id, episode_id, created_at_key DESC, entry_id DESC);
        """
    )


class SqliteEpisodicReinterpretationStore(
    IEpisodicRecallBufferStore,
    IEpisodicReinterpretationJournalStore,
):
    """recall buffer と reinterpretation journal を同じ SQLite 接続で保持する。"""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        apply_migrations(
            connection,
            namespace=_SCHEMA_NAMESPACE,
            migrations=[SqliteMigration(1, _init_schema_v1)],
        )

    @classmethod
    def connect(cls, database_path: str) -> SqliteEpisodicReinterpretationStore:
        conn = sqlite3.connect(database_path, check_same_thread=False)
        store = cls(conn)
        conn.commit()
        return store

    def append(self, observation: EpisodicRecallObservation) -> None:
        payload = json.dumps(_recall_to_payload(observation), ensure_ascii=False)
        self._conn.execute(
            """
            INSERT OR IGNORE INTO episodic_recall_observations
                (player_id, recall_id, episode_id, recalled_at_key, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                observation.player_id,
                observation.recall_id,
                observation.episode_id,
                _dt_key(observation.recalled_at),
                payload,
            ),
        )
        self._conn.commit()

    def peek_batch(
        self,
        player_id: int,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        if batch_size <= 0 or max_contexts_per_episode <= 0:
            return ()
        cur = self._conn.execute(
            """
            SELECT payload_json
            FROM episodic_recall_observations
            WHERE player_id = ?
            ORDER BY recalled_at_key ASC, recall_id ASC
            """,
            (player_id,),
        )
        rows = [_payload_to_recall(json.loads(str(r[0]))) for r in cur.fetchall()]
        selected: list[str] = []
        counts: dict[str, int] = {}
        out: list[EpisodicRecallObservation] = []
        for row in rows:
            if row.episode_id not in counts:
                if len(selected) >= batch_size:
                    continue
                selected.append(row.episode_id)
                counts[row.episode_id] = 0
            if counts[row.episode_id] >= max_contexts_per_episode:
                continue
            counts[row.episode_id] += 1
            out.append(row)
        return tuple(out)

    def mark_processed(self, player_id: int, recall_ids: tuple[str, ...]) -> None:
        if not recall_ids:
            return
        placeholders = ",".join("?" for _ in recall_ids)
        self._conn.execute(
            f"""
            DELETE FROM episodic_recall_observations
            WHERE player_id = ? AND recall_id IN ({placeholders})
            """,
            (player_id, *recall_ids),
        )
        self._conn.commit()

    def pending_count(self, player_id: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS c FROM episodic_recall_observations WHERE player_id = ?",
            (player_id,),
        )
        return int(cur.fetchone()[0])

    def put_active(self, entry: EpisodicReinterpretationEntry) -> None:
        if entry.status != EpisodicReinterpretationStatus.ACTIVE:
            raise ValueError("put_active requires an active entry")
        cur = self._conn.cursor()
        active_rows = cur.execute(
            """
            SELECT payload_json FROM episodic_reinterpretation_journal
            WHERE player_id = ? AND episode_id = ? AND status = ?
            """,
            (entry.player_id, entry.episode_id, EpisodicReinterpretationStatus.ACTIVE.value),
        ).fetchall()
        for row in active_rows:
            old = _payload_to_entry(json.loads(str(row[0])))
            superseded = EpisodicReinterpretationEntry(
                entry_id=old.entry_id,
                player_id=old.player_id,
                episode_id=old.episode_id,
                created_at=old.created_at,
                turn_index=old.turn_index,
                current_interpretation=old.current_interpretation,
                current_recall_text=old.current_recall_text,
                source_recall_ids=old.source_recall_ids,
                status=EpisodicReinterpretationStatus.SUPERSEDED,
                superseded_at=entry.created_at,
            )
            cur.execute(
                """
                UPDATE episodic_reinterpretation_journal
                SET status = ?, payload_json = ?
                WHERE player_id = ? AND entry_id = ?
                """,
                (
                    EpisodicReinterpretationStatus.SUPERSEDED.value,
                    json.dumps(_entry_to_payload(superseded), ensure_ascii=False),
                    old.player_id,
                    old.entry_id,
                ),
            )
        cur.execute(
            """
            INSERT OR REPLACE INTO episodic_reinterpretation_journal
                (player_id, entry_id, episode_id, created_at_key, status, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.player_id,
                entry.entry_id,
                entry.episode_id,
                _dt_key(entry.created_at),
                entry.status.value,
                json.dumps(_entry_to_payload(entry), ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def get_active(
        self,
        player_id: int,
        episode_id: str,
    ) -> EpisodicReinterpretationEntry | None:
        cur = self._conn.execute(
            """
            SELECT payload_json FROM episodic_reinterpretation_journal
            WHERE player_id = ? AND episode_id = ? AND status = ?
            ORDER BY created_at_key DESC, entry_id DESC
            LIMIT 1
            """,
            (player_id, episode_id, EpisodicReinterpretationStatus.ACTIVE.value),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _payload_to_entry(json.loads(str(row[0])))

    def list_by_episode(
        self,
        player_id: int,
        episode_id: str,
    ) -> list[EpisodicReinterpretationEntry]:
        cur = self._conn.execute(
            """
            SELECT payload_json FROM episodic_reinterpretation_journal
            WHERE player_id = ? AND episode_id = ?
            ORDER BY created_at_key DESC, entry_id DESC
            """,
            (player_id, episode_id),
        )
        return [_payload_to_entry(json.loads(str(r[0]))) for r in cur.fetchall()]


__all__ = ["SqliteEpisodicReinterpretationStore"]
