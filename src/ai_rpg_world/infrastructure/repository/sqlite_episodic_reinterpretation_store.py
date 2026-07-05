"""想起後再解釈の SQLite ストア。

Phase 3 Step 3d-3 (Issue #470): legacy player_id 版を撤去し、being_id 版のみを
残した。schema v3 で legacy 2 テーブル
(``episodic_recall_observations`` / ``episodic_reinterpretation_journal``) も
DROP される。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.llm.services._episodic_recall_batch import (
    select_episode_batched,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import EpisodicRecallObservation
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import EpisodicReinterpretationEntry
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import EpisodicReinterpretationStatus
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import EpisodicRecallBufferRepository
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import EpisodicReinterpretationJournalRepository
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
        "prediction_context_id": row.prediction_context_id,
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
        # U1: 旧 payload にはキー自体が無いので None に倒す (後方互換)。
        prediction_context_id=data.get("prediction_context_id"),
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


def _init_schema_v2_by_being(connection: sqlite3.Connection) -> None:
    """Phase 3 Step 3d-1: being_id keyed の並走テーブルを追加。

    legacy テーブルはそのまま残し、新 API は本 v2 テーブルに書き込む
    (= caller 移行 = Step 3d-2 後、Step 3d-3 で legacy テーブルごと撤去予定)。
    memory_link の v4 と同じパターン。

    ``player_id`` 列を残す理由: ``payload_json`` の中にも ``player_id`` は
    エンコード済だが、SQL WHERE で player_id を絞り込みたい運用 (= 監査・
    debug script からの読み出し) を素早く出来るよう列としても保持する。
    また ``EpisodicReinterpretationEntry`` / ``EpisodicRecallObservation`` VO
    が ``player_id`` フィールドを必須にしているため、読み戻し時に再構築できる
    冗長性を維持する目的もある。Step 3d-3 で legacy 撤去後は本列を一次キーから
    外す方針は維持される (= PK は引き続き being_id 経路)。
    """
    connection.executescript(
        """
        CREATE TABLE episodic_recall_observations_by_being (
            being_id_value TEXT NOT NULL,
            recall_id TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            recalled_at_key REAL NOT NULL,
            payload_json TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            PRIMARY KEY (being_id_value, recall_id)
        );
        CREATE INDEX idx_episodic_recall_observations_by_being_pending
            ON episodic_recall_observations_by_being
                (being_id_value, recalled_at_key ASC, recall_id ASC);

        CREATE TABLE episodic_reinterpretation_journal_by_being (
            being_id_value TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            created_at_key REAL NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            PRIMARY KEY (being_id_value, entry_id)
        );
        CREATE INDEX idx_episodic_reinterpretation_by_being_active
            ON episodic_reinterpretation_journal_by_being
                (being_id_value, episode_id, status);
        CREATE INDEX idx_episodic_reinterpretation_by_being_episode_time
            ON episodic_reinterpretation_journal_by_being
                (being_id_value, episode_id, created_at_key DESC, entry_id DESC);
        """
    )


def _init_schema_v3_drop_legacy(connection: sqlite3.Connection) -> None:
    """Phase 3 Step 3d-3: legacy player_id keyed のテーブルを撤去。

    Step 3d-2 で全 caller が ``*_by_being`` API に切り替わったため、player_id
    keyed の旧 2 テーブル/index は参照されなくなった。schema migration で
    DROP して DB ファイル上にも残らないようにする。semantic v3 /
    memory_link v5 と同型。
    """
    connection.executescript(
        """
        DROP INDEX IF EXISTS idx_episodic_recall_observations_pending;
        DROP INDEX IF EXISTS idx_episodic_reinterpretation_active;
        DROP INDEX IF EXISTS idx_episodic_reinterpretation_episode_time;
        DROP TABLE IF EXISTS episodic_recall_observations;
        DROP TABLE IF EXISTS episodic_reinterpretation_journal;
        """
    )


class SqliteEpisodicReinterpretationStore(
    EpisodicRecallBufferRepository,
    EpisodicReinterpretationJournalRepository,
):
    """recall buffer と reinterpretation journal を同じ SQLite 接続で保持する。"""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        apply_migrations(
            connection,
            namespace=_SCHEMA_NAMESPACE,
            migrations=[
                SqliteMigration(1, _init_schema_v1),
                SqliteMigration(2, _init_schema_v2_by_being),
                SqliteMigration(3, _init_schema_v3_drop_legacy),
            ],
        )

    @classmethod
    def connect(cls, database_path: str) -> SqliteEpisodicReinterpretationStore:
        conn = sqlite3.connect(database_path, check_same_thread=False)
        store = cls(conn)
        conn.commit()
        return store

    def append_by_being(
        self, being_id: BeingId, observation: EpisodicRecallObservation
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(observation, EpisodicRecallObservation):
            raise TypeError("observation must be EpisodicRecallObservation")
        payload = json.dumps(_recall_to_payload(observation), ensure_ascii=False)
        self._conn.execute(
            """
            INSERT OR IGNORE INTO episodic_recall_observations_by_being
                (being_id_value, recall_id, episode_id, recalled_at_key,
                 payload_json, player_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                being_id.value,
                observation.recall_id,
                observation.episode_id,
                _dt_key(observation.recalled_at),
                payload,
                observation.player_id,
            ),
        )
        self._conn.commit()

    def peek_batch_by_being(
        self,
        being_id: BeingId,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if batch_size <= 0 or max_contexts_per_episode <= 0:
            return ()
        cur = self._conn.execute(
            """
            SELECT payload_json
            FROM episodic_recall_observations_by_being
            WHERE being_id_value = ?
            ORDER BY recalled_at_key ASC, recall_id ASC
            """,
            (being_id.value,),
        )
        rows = [_payload_to_recall(json.loads(str(r[0]))) for r in cur.fetchall()]
        return select_episode_batched(
            rows,
            batch_size=batch_size,
            max_contexts_per_episode=max_contexts_per_episode,
        )

    def mark_processed_by_being(
        self, being_id: BeingId, recall_ids: tuple[str, ...]
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not recall_ids:
            return
        placeholders = ",".join("?" for _ in recall_ids)
        self._conn.execute(
            f"""
            DELETE FROM episodic_recall_observations_by_being
            WHERE being_id_value = ? AND recall_id IN ({placeholders})
            """,
            (being_id.value, *recall_ids),
        )
        self._conn.commit()

    def pending_count_by_being(self, being_id: BeingId) -> int:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT COUNT(*) AS c FROM episodic_recall_observations_by_being
            WHERE being_id_value = ?
            """,
            (being_id.value,),
        )
        return int(cur.fetchone()[0])

    def put_active_by_being(
        self, being_id: BeingId, entry: EpisodicReinterpretationEntry
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entry, EpisodicReinterpretationEntry):
            raise TypeError("entry must be EpisodicReinterpretationEntry")
        if entry.status != EpisodicReinterpretationStatus.ACTIVE:
            raise ValueError("put_active_by_being requires an active entry")
        cur = self._conn.cursor()
        active_rows = cur.execute(
            """
            SELECT payload_json FROM episodic_reinterpretation_journal_by_being
            WHERE being_id_value = ? AND episode_id = ? AND status = ?
            """,
            (being_id.value, entry.episode_id, EpisodicReinterpretationStatus.ACTIVE.value),
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
                UPDATE episodic_reinterpretation_journal_by_being
                SET status = ?, payload_json = ?
                WHERE being_id_value = ? AND entry_id = ?
                """,
                (
                    EpisodicReinterpretationStatus.SUPERSEDED.value,
                    json.dumps(_entry_to_payload(superseded), ensure_ascii=False),
                    being_id.value,
                    old.entry_id,
                ),
            )
        cur.execute(
            """
            INSERT OR REPLACE INTO episodic_reinterpretation_journal_by_being
                (being_id_value, entry_id, episode_id, created_at_key, status,
                 payload_json, player_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                being_id.value,
                entry.entry_id,
                entry.episode_id,
                _dt_key(entry.created_at),
                entry.status.value,
                json.dumps(_entry_to_payload(entry), ensure_ascii=False),
                entry.player_id,
            ),
        )
        self._conn.commit()

    def get_active_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
    ) -> EpisodicReinterpretationEntry | None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT payload_json FROM episodic_reinterpretation_journal_by_being
            WHERE being_id_value = ? AND episode_id = ? AND status = ?
            ORDER BY created_at_key DESC, entry_id DESC
            LIMIT 1
            """,
            (being_id.value, episode_id, EpisodicReinterpretationStatus.ACTIVE.value),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _payload_to_entry(json.loads(str(row[0])))

    def list_by_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
    ) -> list[EpisodicReinterpretationEntry]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT payload_json FROM episodic_reinterpretation_journal_by_being
            WHERE being_id_value = ? AND episode_id = ?
            ORDER BY created_at_key DESC, entry_id DESC
            """,
            (being_id.value, episode_id),
        )
        return [_payload_to_entry(json.loads(str(r[0]))) for r in cur.fetchall()]


    def list_pending_by_being(
        self, being_id: BeingId
    ) -> list[EpisodicRecallObservation]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT payload_json FROM episodic_recall_observations_by_being
            WHERE being_id_value = ?
            ORDER BY recalled_at_key ASC, recall_id ASC
            """,
            (being_id.value,),
        )
        return [_payload_to_recall(json.loads(str(r[0]))) for r in cur.fetchall()]

    def replace_all_pending_by_being(
        self,
        being_id: BeingId,
        observations: list[EpisodicRecallObservation],
    ) -> None:
        """recall buffer の pending を ``observations`` で完全置換する (single transaction)。"""
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(observations, list):
            raise TypeError("observations must be list")
        for o in observations:
            if not isinstance(o, EpisodicRecallObservation):
                raise TypeError(
                    "observations elements must be EpisodicRecallObservation"
                )
        # 注意: 明示的 BEGIN は打たない (implicit transaction との衝突回避)。
        # 詳細は sqlite_semantic_memory_store.py の同コメント参照。
        try:
            self._conn.execute(
                "DELETE FROM episodic_recall_observations_by_being WHERE being_id_value = ?",
                (being_id.value,),
            )
            for obs in observations:
                self._conn.execute(
                    """
                    INSERT INTO episodic_recall_observations_by_being
                        (being_id_value, recall_id, episode_id, recalled_at_key,
                         payload_json, player_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        being_id.value,
                        obs.recall_id,
                        obs.episode_id,
                        _dt_key(obs.recalled_at),
                        json.dumps(_recall_to_payload(obs), ensure_ascii=False),
                        obs.player_id,
                    ),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def list_all_by_being(
        self, being_id: BeingId
    ) -> list[EpisodicReinterpretationEntry]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            """
            SELECT payload_json FROM episodic_reinterpretation_journal_by_being
            WHERE being_id_value = ?
            ORDER BY created_at_key ASC, entry_id ASC
            """,
            (being_id.value,),
        )
        return [_payload_to_entry(json.loads(str(r[0]))) for r in cur.fetchall()]

    def replace_all_by_being(
        self,
        being_id: BeingId,
        entries: list[EpisodicReinterpretationEntry],
    ) -> None:
        """journal を ``entries`` で完全置換する (single transaction)。"""
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entries, list):
            raise TypeError("entries must be list")
        for e in entries:
            if not isinstance(e, EpisodicReinterpretationEntry):
                raise TypeError(
                    "entries elements must be EpisodicReinterpretationEntry"
                )
        # 注意: 明示的 BEGIN は打たない (implicit transaction との衝突回避)。
        # 詳細は sqlite_semantic_memory_store.py の同コメント参照。
        try:
            self._conn.execute(
                "DELETE FROM episodic_reinterpretation_journal_by_being WHERE being_id_value = ?",
                (being_id.value,),
            )
            for entry in entries:
                self._conn.execute(
                    """
                    INSERT INTO episodic_reinterpretation_journal_by_being
                        (being_id_value, entry_id, episode_id, created_at_key,
                         status, payload_json, player_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        being_id.value,
                        entry.entry_id,
                        entry.episode_id,
                        _dt_key(entry.created_at),
                        entry.status.value,
                        json.dumps(_entry_to_payload(entry), ensure_ascii=False),
                        entry.player_id,
                    ),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise


__all__ = ["SqliteEpisodicReinterpretationStore"]
