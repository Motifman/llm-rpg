"""SemanticMemoryRepository の SQLite 実装。

Phase 3 Step 3b-3 (Issue #470): legacy player_id 版を撤去し、being_id 版のみ
を残した。schema v3 で legacy テーブルも DROP される。
"""

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

    def add_by_being(self, being_id: BeingId, entry: SemanticMemoryEntry) -> None:
        """being_id keyed で entry を upsert する。

        ``created_at`` も上書き対象に含める設計判断: Entry 側が「最終更新時刻」
        相当として渡してくる前提。``list_for_being`` が ``ORDER BY created_at DESC``
        なので、更新で再 hot 化される効果を期待。「最初の登録時刻」を保持
        したいなら caller 側で既存 entry を re-read して ``created_at`` を保った
        まま渡す責務とする。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entry, SemanticMemoryEntry):
            raise TypeError("entry must be SemanticMemoryEntry")
        self._upsert_entry_no_commit(being_id, entry)
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
            row_keys = row.keys()
            raw_support = (
                json.loads(str(row["support_evidence_ids_json"]))
                if "support_evidence_ids_json" in row_keys
                else []
            )
            raw_contradict = (
                json.loads(str(row["contradict_evidence_ids_json"]))
                if "contradict_evidence_ids_json" in row_keys
                else []
            )
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
                    belief_id=str(row["belief_id"]) if "belief_id" in row_keys else "",
                    status=str(row["status"]) if "status" in row_keys else "active",
                    supersedes=(
                        str(row["supersedes"])
                        if ("supersedes" in row_keys and row["supersedes"] is not None)
                        else None
                    ),
                    support_evidence_ids=tuple(str(x) for x in raw_support),
                    contradict_evidence_ids=tuple(str(x) for x in raw_contradict),
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


    def list_cluster_signatures_by_being(self, being_id: BeingId) -> list[str]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT evidence_signature FROM semantic_cluster_signatures_by_being
            WHERE being_id_value = ?
            ORDER BY evidence_signature ASC
            """,
            (being_id.value,),
        )
        return [str(row["evidence_signature"]) for row in cur.fetchall()]

    def replace_all_by_being(
        self,
        being_id: BeingId,
        entries: list[SemanticMemoryEntry],
        cluster_signatures: list[str],
    ) -> None:
        """being_id 配下の entries と cluster_signatures を SQLite トランザクション内で完全置換する。

        Phase 4 Step 4-2a: snapshot restore primitive。delete → insert の 2 段を
        単一トランザクションで実行することで、片方だけ消えた状態を構造的に防ぐ
        (= silent failure 構造的対処方針)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entries, list):
            raise TypeError("entries must be list")
        for e in entries:
            if not isinstance(e, SemanticMemoryEntry):
                raise TypeError("entries elements must be SemanticMemoryEntry")
        if not isinstance(cluster_signatures, list):
            raise TypeError("cluster_signatures must be list")
        for s in cluster_signatures:
            if not isinstance(s, str):
                raise TypeError("cluster_signatures elements must be str")

        # 注意: sqlite3 module は ``isolation_level=''`` (deferred) で
        # 動いており、最初の DML が implicit transaction を開く。明示的に
        # ``BEGIN`` を打つと「既に txn 内」のケースで OperationalError に
        # なるので、ここでは打たない。失敗時 rollback でロールバックする
        # 範囲は「本メソッド内の全 DML」になり、partial state の構造禁止
        # は保たれる (= 既存 store の put_by_being 等と同じパターン)。
        try:
            self._conn.execute(
                "DELETE FROM semantic_memory_entries_by_being WHERE being_id_value = ?",
                (being_id.value,),
            )
            self._conn.execute(
                "DELETE FROM semantic_cluster_signatures_by_being WHERE being_id_value = ?",
                (being_id.value,),
            )
            for entry in entries:
                payload = json.dumps(
                    list(entry.evidence_episode_ids), ensure_ascii=False
                )
                tags_json = json.dumps(list(entry.tags), ensure_ascii=False)
                support_json = json.dumps(
                    list(entry.support_evidence_ids), ensure_ascii=False
                )
                contradict_json = json.dumps(
                    list(entry.contradict_evidence_ids), ensure_ascii=False
                )
                self._conn.execute(
                    """
                    INSERT INTO semantic_memory_entries_by_being (
                        entry_id, being_id_value, text, evidence_episode_ids_json,
                        confidence, created_at, importance_score, tags_json, player_id,
                        belief_id, status, supersedes,
                        support_evidence_ids_json, contradict_evidence_ids_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        entry.belief_id,
                        entry.status,
                        entry.supersedes,
                        support_json,
                        contradict_json,
                    ),
                )
            for sig in cluster_signatures:
                self._conn.execute(
                    """
                    INSERT INTO semantic_cluster_signatures_by_being
                        (being_id_value, evidence_signature)
                    VALUES (?, ?)
                    """,
                    (being_id.value, sig),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def supersede_by_being(
        self,
        being_id: BeingId,
        *,
        old_entry_id: str,
        new_entry: SemanticMemoryEntry,
    ) -> None:
        """old を superseded に更新し、new_entry を upsert する (U3a)。

        ``replace_all_by_being`` と同じ理由で、UPDATE + upsert を単一
        トランザクションで行い、片方だけ反映される状態を構造的に防ぐ。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(old_entry_id, str) or not old_entry_id.strip():
            raise TypeError("old_entry_id must be non-empty str")
        if not isinstance(new_entry, SemanticMemoryEntry):
            raise TypeError("new_entry must be SemanticMemoryEntry")
        try:
            self._conn.execute(
                """
                UPDATE semantic_memory_entries_by_being
                SET status = 'superseded'
                WHERE being_id_value = ? AND entry_id = ?
                """,
                (being_id.value, old_entry_id),
            )
            self._upsert_entry_no_commit(being_id, new_entry)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def update_status_by_being(
        self, being_id: BeingId, entry_id: str, status: str
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise TypeError("entry_id must be non-empty str")
        if not isinstance(status, str):
            raise TypeError("status must be str")
        self._conn.execute(
            """
            UPDATE semantic_memory_entries_by_being
            SET status = ?
            WHERE being_id_value = ? AND entry_id = ?
            """,
            (status, being_id.value, entry_id),
        )
        self._conn.commit()

    def _upsert_entry_no_commit(
        self, being_id: BeingId, entry: SemanticMemoryEntry
    ) -> None:
        """``add_by_being`` と同一の UPSERT を commit なしで実行する内部ヘルパー。

        ``supersede_by_being`` が old の UPDATE と同一トランザクションで
        まとめてコミットするために分離した。
        """
        payload = json.dumps(list(entry.evidence_episode_ids), ensure_ascii=False)
        tags_json = json.dumps(list(entry.tags), ensure_ascii=False)
        support_json = json.dumps(list(entry.support_evidence_ids), ensure_ascii=False)
        contradict_json = json.dumps(
            list(entry.contradict_evidence_ids), ensure_ascii=False
        )
        self._conn.execute(
            """
            INSERT INTO semantic_memory_entries_by_being (
                entry_id, being_id_value, text, evidence_episode_ids_json,
                confidence, created_at, importance_score, tags_json, player_id,
                belief_id, status, supersedes,
                support_evidence_ids_json, contradict_evidence_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(being_id_value, entry_id) DO UPDATE SET
                text = excluded.text,
                evidence_episode_ids_json = excluded.evidence_episode_ids_json,
                confidence = excluded.confidence,
                created_at = excluded.created_at,
                importance_score = excluded.importance_score,
                tags_json = excluded.tags_json,
                player_id = excluded.player_id,
                belief_id = excluded.belief_id,
                status = excluded.status,
                supersedes = excluded.supersedes,
                support_evidence_ids_json = excluded.support_evidence_ids_json,
                contradict_evidence_ids_json = excluded.contradict_evidence_ids_json
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
                entry.belief_id,
                entry.status,
                entry.supersedes,
                support_json,
                contradict_json,
            ),
        )


__all__ = ["SqliteSemanticMemoryStore"]
