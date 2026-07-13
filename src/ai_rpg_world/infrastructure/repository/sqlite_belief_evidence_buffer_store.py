"""BeliefEvidence バッファの SQLite ストア。

U2 (証拠台帳統一設計)。``sqlite_episodic_reinterpretation_store.py`` と
同型の being_id keyed テーブル 1 本。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.repository.belief_evidence_buffer_repository import (
    BeliefEvidenceBufferRepository,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)

_SCHEMA_NAMESPACE = "belief-evidence-buffer-v1"


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


def _evidence_to_payload(evidence: BeliefEvidence) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "source_kind": evidence.source_kind.value,
        "episode_ids": list(evidence.episode_ids),
        "cue_signature": evidence.cue_signature,
        "text": evidence.text,
        "salience": evidence.salience,
        "occurred_at": _dt_to_text(evidence.occurred_at),
        "tick": evidence.tick,
        # U4 (予測誤差統一設計): この evidence 発生ターンで in-context だった
        # belief_id 群。固着処理が strengthen/contradict の対応づけに使う。
        # payload JSON 内なので schema 変更不要 (source_speaker と同様)。
        "in_context_belief_ids": list(evidence.in_context_belief_ids),
        # P9 (伝聞): HEARSAY evidence の話者 (payload JSON 内なので schema 変更不要)。
        "source_speaker": evidence.source_speaker,
    }


def _payload_to_evidence(data: dict[str, Any]) -> BeliefEvidence:
    return BeliefEvidence(
        evidence_id=str(data["evidence_id"]),
        source_kind=BeliefEvidenceSourceKind(str(data["source_kind"])),
        episode_ids=tuple(str(x) for x in data.get("episode_ids", ())),
        cue_signature=str(data["cue_signature"]),
        text=str(data["text"]),
        salience=str(data["salience"]),
        occurred_at=_text_to_dt(str(data["occurred_at"])),
        tick=int(data["tick"]) if data.get("tick") is not None else None,
        # 旧 payload (U4 前に書かれた行) には本 key が無いので空タプルに
        # フォールバックする。attribution 機構 OFF と同じ扱いで後方互換。
        in_context_belief_ids=tuple(
            str(x) for x in data.get("in_context_belief_ids", ())
        ),
        source_speaker=(
            str(data["source_speaker"])
            if data.get("source_speaker") is not None
            else None
        ),
    )


def _init_schema_v1(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE belief_evidence_buffer_by_being (
            being_id_value TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            occurred_at_key REAL NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (being_id_value, evidence_id)
        );
        CREATE INDEX idx_belief_evidence_buffer_by_being_order
            ON belief_evidence_buffer_by_being
                (being_id_value, occurred_at_key ASC, evidence_id ASC);
        """
    )


class SqliteBeliefEvidenceBufferStore(BeliefEvidenceBufferRepository):
    """``BeliefEvidence`` バッファを SQLite に保持する。"""

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
    def connect(cls, database_path: str) -> "SqliteBeliefEvidenceBufferStore":
        conn = sqlite3.connect(database_path, check_same_thread=False)
        store = cls(conn)
        conn.commit()
        return store

    def append_by_being(self, being_id: BeingId, evidence: BeliefEvidence) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(evidence, BeliefEvidence):
            raise TypeError("evidence must be BeliefEvidence")
        payload = json.dumps(_evidence_to_payload(evidence), ensure_ascii=False)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO belief_evidence_buffer_by_being
                (being_id_value, evidence_id, occurred_at_key, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                being_id.value,
                evidence.evidence_id,
                _dt_key(evidence.occurred_at),
                payload,
            ),
        )
        self._conn.commit()

    def list_all_by_being(self, being_id: BeingId) -> list[BeliefEvidence]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT payload_json FROM belief_evidence_buffer_by_being
            WHERE being_id_value = ?
            ORDER BY occurred_at_key ASC, evidence_id ASC
            """,
            (being_id.value,),
        )
        return [_payload_to_evidence(json.loads(str(r[0]))) for r in cur.fetchall()]

    def remove_by_being(
        self, being_id: BeingId, evidence_ids: Iterable[str]
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        ids = [str(eid) for eid in evidence_ids]
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        self._conn.execute(
            f"""
            DELETE FROM belief_evidence_buffer_by_being
            WHERE being_id_value = ? AND evidence_id IN ({placeholders})
            """,
            (being_id.value, *ids),
        )
        self._conn.commit()

    def replace_all_by_being(
        self,
        being_id: BeingId,
        evidences: list[BeliefEvidence],
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(evidences, list):
            raise TypeError("evidences must be list")
        for e in evidences:
            if not isinstance(e, BeliefEvidence):
                raise TypeError("evidences elements must be BeliefEvidence")
        # 注意: 明示的 BEGIN は打たない (implicit transaction との衝突回避)。
        # 詳細は sqlite_semantic_memory_store.py の同コメント参照。
        try:
            self._conn.execute(
                "DELETE FROM belief_evidence_buffer_by_being WHERE being_id_value = ?",
                (being_id.value,),
            )
            for evidence in evidences:
                self._conn.execute(
                    """
                    INSERT INTO belief_evidence_buffer_by_being
                        (being_id_value, evidence_id, occurred_at_key, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        being_id.value,
                        evidence.evidence_id,
                        _dt_key(evidence.occurred_at),
                        json.dumps(
                            _evidence_to_payload(evidence), ensure_ascii=False
                        ),
                    ),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise


__all__ = ["SqliteBeliefEvidenceBufferStore"]
