"""SemanticMemoryRepository の SQLite 実装。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import SemanticMemoryRepository
from ai_rpg_world.infrastructure.repository.sqlite_memory_graph_schema import (
    apply_memory_graph_migrations,
)


def _dt_from_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _dt_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


class SqliteSemanticMemoryStore(SemanticMemoryRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        apply_memory_graph_migrations(connection)

    def add(self, entry: SemanticMemoryEntry) -> None:
        payload = json.dumps(list(entry.evidence_episode_ids), ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO semantic_memory_entries (
                entry_id, player_id, text, evidence_episode_ids_json, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(entry_id) DO UPDATE SET
                player_id = excluded.player_id,
                text = excluded.text,
                evidence_episode_ids_json = excluded.evidence_episode_ids_json,
                confidence = excluded.confidence,
                created_at = excluded.created_at
            """,
            (
                entry.entry_id,
                entry.player_id,
                entry.text,
                payload,
                float(entry.confidence),
                _dt_to_iso(entry.created_at),
            ),
        )
        self._conn.commit()

    def list_for_player(self, player_id: int) -> list[SemanticMemoryEntry]:
        cur = self._conn.execute(
            """
            SELECT * FROM semantic_memory_entries
            WHERE player_id = ?
            ORDER BY created_at DESC
            """,
            (player_id,),
        )
        out: list[SemanticMemoryEntry] = []
        for row in cur.fetchall():
            raw_ids = json.loads(str(row["evidence_episode_ids_json"]))
            eids = tuple(str(x) for x in raw_ids)
            out.append(
                SemanticMemoryEntry(
                    entry_id=str(row["entry_id"]),
                    player_id=int(row["player_id"]),
                    text=str(row["text"]),
                    evidence_episode_ids=eids,
                    confidence=float(row["confidence"]),
                    created_at=_dt_from_iso(str(row["created_at"])),
                )
            )
        return out

    def register_cluster_signature_if_new(self, player_id: int, evidence_signature: str) -> bool:
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO semantic_cluster_signatures (player_id, evidence_signature)
            VALUES (?, ?)
            """,
            (player_id, evidence_signature),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ===== Phase 3 Step 3b-1: being_id 版を並走追加 =====

    def add_by_being(self, being_id: BeingId, entry: SemanticMemoryEntry) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entry, SemanticMemoryEntry):
            raise TypeError("entry must be SemanticMemoryEntry")
        payload = json.dumps(list(entry.evidence_episode_ids), ensure_ascii=False)
        tags_json = json.dumps(list(entry.tags), ensure_ascii=False)
        self._conn.execute(
            """
            INSERT INTO semantic_memory_entries_by_being (
                entry_id, being_id_value, text, evidence_episode_ids_json,
                confidence, created_at, importance_score, tags_json, player_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(being_id_value, entry_id) DO UPDATE SET
                text = excluded.text,
                evidence_episode_ids_json = excluded.evidence_episode_ids_json,
                confidence = excluded.confidence,
                created_at = excluded.created_at,
                importance_score = excluded.importance_score,
                tags_json = excluded.tags_json,
                player_id = excluded.player_id
            """,
            (
                entry.entry_id,
                being_id.value,
                entry.text,
                payload,
                float(entry.confidence),
                _dt_to_iso(entry.created_at),
                int(entry.importance_score),
                tags_json,
                entry.player_id,
            ),
        )
        self._conn.commit()

    def list_for_being(self, being_id: BeingId) -> list[SemanticMemoryEntry]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT * FROM semantic_memory_entries_by_being
            WHERE being_id_value = ?
            ORDER BY created_at DESC
            """,
            (being_id.value,),
        )
        out: list[SemanticMemoryEntry] = []
        for row in cur.fetchall():
            raw_ids = json.loads(str(row["evidence_episode_ids_json"]))
            eids = tuple(str(x) for x in raw_ids)
            raw_tags = json.loads(str(row["tags_json"]))
            tags = tuple(str(x) for x in raw_tags)
            out.append(
                SemanticMemoryEntry(
                    entry_id=str(row["entry_id"]),
                    player_id=int(row["player_id"]),
                    text=str(row["text"]),
                    evidence_episode_ids=eids,
                    confidence=float(row["confidence"]),
                    created_at=_dt_from_iso(str(row["created_at"])),
                    importance_score=int(row["importance_score"]),
                    tags=tags,
                )
            )
        return out

    def register_cluster_signature_if_new_by_being(
        self, being_id: BeingId, evidence_signature: str
    ) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(evidence_signature, str):
            raise TypeError("evidence_signature must be str")
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO semantic_cluster_signatures_by_being
                (being_id_value, evidence_signature)
            VALUES (?, ?)
            """,
            (being_id.value, evidence_signature),
        )
        self._conn.commit()
        return cur.rowcount > 0


__all__ = ["SqliteSemanticMemoryStore"]
