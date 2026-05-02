"""v2 SubjectiveEpisode の SQLite 永続化（episode_cues / memory_links）。

レガシー `episode_memories` / SqliteEpisodeMemoryStore とは別 schema。
同一 .sqlite ファイルに共存させることは可能（テーブル名が異なる）。
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from ai_rpg_world.application.llm.contracts.dtos import (
    SubjectiveEpisode,
    subjective_episode_index_strings,
)
from ai_rpg_world.application.llm.contracts.interfaces import ISubjectiveEpisodeStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.llm.subjective_episode_sqlite_codec import (
    subjective_episode_from_json,
    subjective_episode_to_json,
)
from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)

SUBJECTIVE_EPISODE_V2_NAMESPACE = "subjective-episode-v2"


def _connect(db_path: Union[str, Path]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _apply_v2_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS subjective_episodes (
            agent_id INTEGER NOT NULL,
            episode_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_recalled_at TEXT,
            recall_count INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (agent_id, episode_id)
        );
        CREATE INDEX IF NOT EXISTS idx_subjective_episodes_agent_created
            ON subjective_episodes(agent_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS episode_cues (
            agent_id INTEGER NOT NULL,
            episode_id TEXT NOT NULL,
            cue_type TEXT NOT NULL,
            cue_key TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (agent_id, episode_id, cue_key),
            FOREIGN KEY (agent_id, episode_id)
                REFERENCES subjective_episodes(agent_id, episode_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_episode_cues_agent_cue
            ON episode_cues(agent_id, cue_key);

        CREATE TABLE IF NOT EXISTS memory_links (
            agent_id INTEGER NOT NULL,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            link_type TEXT NOT NULL,
            strength REAL NOT NULL,
            evidence_count INTEGER NOT NULL DEFAULT 1,
            last_reinforced_at TEXT,
            created_reason TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (agent_id, source_id, target_id, link_type),
            FOREIGN KEY (agent_id, source_id)
                REFERENCES subjective_episodes(agent_id, episode_id) ON DELETE CASCADE,
            FOREIGN KEY (agent_id, target_id)
                REFERENCES subjective_episodes(agent_id, episode_id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()


_MIGRATIONS: Tuple[SqliteMigration, ...] = (
    SqliteMigration(version=1, apply=_apply_v2_schema),
)


def _cue_type_for_canonical_key(cue_key: str) -> str:
    s = cue_key.strip()
    if ":" in s:
        return s.split(":", 1)[0].strip() or "legacy"
    return "legacy"


def _parse_created_at(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SqliteSubjectiveEpisodeStore(ISubjectiveEpisodeStore):
    """SubjectiveEpisode（v2）+ cue 逆引き index + memory_links。"""

    def __init__(
        self,
        db_path: Union[str, Path],
        *,
        max_entries_per_player: int = 2000,
        max_links_per_episode: int = 5,
        max_cue_lookup_candidates: int = 100,
    ) -> None:
        if max_entries_per_player < 1:
            raise ValueError("max_entries_per_player must be >= 1")
        if max_links_per_episode < 0:
            raise ValueError("max_links_per_episode must be >= 0")
        if max_cue_lookup_candidates < 1:
            raise ValueError("max_cue_lookup_candidates must be >= 1")
        self._db_path = str(db_path)
        self._max_entries = max_entries_per_player
        self._max_links = max_links_per_episode
        self._max_cue_candidates = max_cue_lookup_candidates
        conn = _connect(self._db_path)
        try:
            apply_migrations(
                conn,
                namespace=SUBJECTIVE_EPISODE_V2_NAMESPACE,
                migrations=_MIGRATIONS,
            )
        finally:
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        return _connect(self._db_path)

    def put(self, player_id: PlayerId, episode: SubjectiveEpisode) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        if episode.agent_id != player_id.value:
            raise ValueError("episode.agent_id must match player_id")

        aid = player_id.value
        index_strings = subjective_episode_index_strings(episode)
        payload = subjective_episode_to_json(episode)
        lr = episode.last_recalled_at.isoformat() if episode.last_recalled_at else None

        conn = self._conn()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO subjective_episodes (
                    agent_id, episode_id, created_at, last_recalled_at, recall_count, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id, episode_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    last_recalled_at = excluded.last_recalled_at,
                    recall_count = excluded.recall_count,
                    payload_json = excluded.payload_json
                """,
                (
                    aid,
                    episode.episode_id,
                    episode.created_at.isoformat(),
                    lr,
                    episode.recall_count,
                    payload,
                ),
            )
            conn.execute(
                "DELETE FROM episode_cues WHERE agent_id = ? AND episode_id = ?",
                (aid, episode.episode_id),
            )
            conn.execute(
                "DELETE FROM memory_links WHERE agent_id = ? AND source_id = ?",
                (aid, episode.episode_id),
            )
            for ck in index_strings:
                ck_norm = ck.strip()
                if not ck_norm:
                    continue
                conn.execute(
                    """
                    INSERT INTO episode_cues (
                        agent_id, episode_id, cue_type, cue_key, confidence
                    ) VALUES (?, ?, ?, ?, 1.0)
                    """,
                    (aid, episode.episode_id, _cue_type_for_canonical_key(ck_norm), ck_norm),
                )
            self._insert_links(conn, aid, episode, tuple(index_strings))
            self._evict_excess(conn, aid)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _insert_links(
        self,
        conn: sqlite3.Connection,
        agent_id: int,
        ep: SubjectiveEpisode,
        index_strings: Tuple[str, ...],
    ) -> None:
        if self._max_links == 0 or not index_strings:
            return
        keys = tuple(k.strip() for k in index_strings if k.strip())
        if not keys:
            return
        placeholders = ",".join("?" * len(keys))
        sql = f"""
            SELECT DISTINCT episode_id FROM episode_cues
            WHERE agent_id = ? AND cue_key IN ({placeholders}) AND episode_id != ?
            LIMIT ?
        """
        cur = conn.execute(
            sql,
            (agent_id, *keys, ep.episode_id, self._max_cue_candidates),
        )
        candidate_ids = [str(r[0]) for r in cur.fetchall()]
        if not candidate_ids:
            return

        scored: List[Tuple[float, str, str, int]] = []
        for oid in candidate_ids:
            overlap_row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM episode_cues c1
                INNER JOIN episode_cues c2
                  ON c1.agent_id = c2.agent_id AND c1.cue_key = c2.cue_key
                WHERE c1.agent_id = ? AND c1.episode_id = ? AND c2.episode_id = ?
                """,
                (agent_id, ep.episode_id, oid),
            ).fetchone()
            overlap = int(overlap_row["n"]) if overlap_row else 0
            if overlap == 0:
                continue
            meta = conn.execute(
                """
                SELECT created_at, recall_count FROM subjective_episodes
                WHERE agent_id = ? AND episode_id = ?
                """,
                (agent_id, oid),
            ).fetchone()
            if meta is None:
                continue
            old_ts = _parse_created_at(str(meta["created_at"]))
            old_recall = int(meta["recall_count"])
            hours_apart = abs((ep.created_at - old_ts).total_seconds()) / 3600.0
            temporal_bonus = max(0.0, 18.0 - min(hours_apart, 72.0) * 0.25)
            prior_bonus = 8.0 if old_ts < ep.created_at else 0.0
            recall_bonus = 12.0 if old_recall >= 1 else 0.0
            score = overlap * 14.0 + temporal_bonus + prior_bonus + recall_bonus
            link_kind = "co_recalled" if old_recall >= 1 else "spatial"
            scored.append((score, oid, link_kind, overlap))

        scored.sort(key=lambda t: t[0], reverse=True)
        used_targets: set[str] = set()
        rows_written = 0
        for score, oid, link_kind, overlap in scored:
            if rows_written >= self._max_links:
                break
            if oid in used_targets:
                continue
            used_targets.add(oid)
            strength = min(1.0, 0.18 + 0.07 * overlap)
            conn.execute(
                """
                INSERT INTO memory_links (
                    agent_id, source_id, target_id, link_type, strength,
                    evidence_count, last_reinforced_at, created_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    ep.episode_id,
                    oid,
                    link_kind,
                    strength,
                    overlap,
                    None,
                    f"cue_overlap_score={score:.2f}",
                ),
            )
            rows_written += 1

        temporal_row = conn.execute(
            """
            SELECT episode_id, created_at FROM subjective_episodes
            WHERE agent_id = ? AND datetime(created_at) < datetime(?)
            ORDER BY created_at DESC LIMIT 1
            """,
            (agent_id, ep.created_at.isoformat()),
        ).fetchone()
        if (
            temporal_row is not None
            and rows_written < self._max_links
            and str(temporal_row["episode_id"]) != ep.episode_id
        ):
            tid = str(temporal_row["episode_id"])
            if tid not in used_targets:
                conn.execute(
                    """
                    INSERT INTO memory_links (
                        agent_id, source_id, target_id, link_type, strength,
                        evidence_count, last_reinforced_at, created_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        agent_id,
                        ep.episode_id,
                        tid,
                        "temporal",
                        0.45,
                        0,
                        None,
                        "chronological_prior",
                    ),
                )

    def _evict_excess(self, conn: sqlite3.Connection, agent_id: int) -> None:
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM subjective_episodes WHERE agent_id = ?",
            (agent_id,),
        )
        n = int(cur.fetchone()["n"])
        if n <= self._max_entries:
            return
        excess = n - self._max_entries
        victims = conn.execute(
            """
            SELECT episode_id FROM subjective_episodes
            WHERE agent_id = ?
            ORDER BY created_at ASC, episode_id ASC
            LIMIT ?
            """,
            (agent_id, excess),
        ).fetchall()
        for row in victims:
            conn.execute(
                "DELETE FROM subjective_episodes WHERE agent_id = ? AND episode_id = ?",
                (agent_id, str(row["episode_id"])),
            )

    def get_by_episode_id(
        self, player_id: PlayerId, episode_id: str
    ) -> Optional[SubjectiveEpisode]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(episode_id, str):
            raise TypeError("episode_id must be str")
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT payload_json FROM subjective_episodes WHERE agent_id = ? AND episode_id = ?",
                (player_id.value, episode_id),
            ).fetchone()
            if row is None:
                return None
            return subjective_episode_from_json(str(row["payload_json"]))
        finally:
            conn.close()

    def list_recent(self, player_id: PlayerId, limit: int) -> List[SubjectiveEpisode]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        if limit == 0:
            return []
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                SELECT payload_json FROM subjective_episodes
                WHERE agent_id = ?
                ORDER BY created_at DESC, episode_id DESC
                LIMIT ?
                """,
                (player_id.value, limit),
            )
            return [subjective_episode_from_json(str(r["payload_json"])) for r in cur.fetchall()]
        finally:
            conn.close()

    def list_all_episodes(self, player_id: PlayerId) -> List[SubjectiveEpisode]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                SELECT payload_json FROM subjective_episodes
                WHERE agent_id = ?
                ORDER BY created_at ASC, episode_id ASC
                """,
                (player_id.value,),
            )
            return [subjective_episode_from_json(str(r["payload_json"])) for r in cur.fetchall()]
        finally:
            conn.close()

    def record_passive_recall(self, player_id: PlayerId, episode_id: str) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(episode_id, str):
            raise TypeError("episode_id must be str")
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT payload_json FROM subjective_episodes WHERE agent_id = ? AND episode_id = ?",
                (player_id.value, episode_id),
            ).fetchone()
            if row is None:
                return
            ep = subjective_episode_from_json(str(row["payload_json"]))
            now = datetime.now()
            updated = replace(
                ep,
                recall_count=ep.recall_count + 1,
                last_recalled_at=now,
            )
            payload = subjective_episode_to_json(updated)
            conn.execute(
                """
                UPDATE subjective_episodes
                SET recall_count = ?, last_recalled_at = ?, payload_json = ?
                WHERE agent_id = ? AND episode_id = ?
                """,
                (
                    updated.recall_count,
                    now.isoformat(),
                    payload,
                    player_id.value,
                    episode_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def count_reflection_journal_entries(self, player_id: PlayerId) -> int:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT payload_json FROM subjective_episodes WHERE agent_id = ?",
                (player_id.value,),
            )
            total = 0
            for row in cur.fetchall():
                ep = subjective_episode_from_json(str(row["payload_json"]))
                total += len(ep.memory_reflection_journal)
            return total
        finally:
            conn.close()

    def list_episode_ids_by_cue_keys(
        self,
        player_id: PlayerId,
        cue_keys: Sequence[str],
        *,
        limit: int = 100,
    ) -> List[str]:
        """Tests / advanced retrievers: cue_key 逆引き（全件スキャンしない）。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        keys = tuple(k.strip() for k in cue_keys if k and k.strip())
        if not keys:
            return []
        conn = self._conn()
        try:
            placeholders = ",".join("?" * len(keys))
            sql = f"""
                SELECT DISTINCT episode_id FROM episode_cues
                WHERE agent_id = ? AND cue_key IN ({placeholders})
                ORDER BY episode_id DESC
                LIMIT ?
            """
            cur = conn.execute(sql, (player_id.value, *keys, limit))
            return [str(r[0]) for r in cur.fetchall()]
        finally:
            conn.close()

    def list_memory_links_from(
        self, player_id: PlayerId, source_episode_id: str
    ) -> List[dict]:
        """テスト・デバッグ用: source_episode_id 起点の memory_links。"""
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                SELECT target_id, link_type, strength, evidence_count, created_reason
                FROM memory_links
                WHERE agent_id = ? AND source_id = ?
                ORDER BY link_type, target_id
                """,
                (player_id.value, source_episode_id),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
