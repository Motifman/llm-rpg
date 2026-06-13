"""IMemoryLinkStore の SQLite 実装（主観エピソード DB と同一ファイル）。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
    effective_link_strength,
    normalize_episode_pair,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    IMemoryLinkStore,
)
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


def _row_to_link(row: sqlite3.Row) -> MemoryLink:
    return MemoryLink(
        link_id=str(row["link_id"]),
        player_id=int(row["player_id"]),
        episode_id_a=str(row["episode_id_a"]),
        episode_id_b=str(row["episode_id_b"]),
        link_type=MemoryLinkType(str(row["link_type"])),
        strength=float(row["strength"]),
        co_activation_count=int(row["co_activation_count"]),
        created_at=_dt_from_iso(str(row["created_at"])),
        last_activated_at=_dt_from_iso(str(row["last_activated_at"])),
        decay_rate=float(row["decay_rate"]),
    )


class SqliteMemoryLinkStore(IMemoryLinkStore):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        apply_memory_graph_migrations(connection)

    def upsert_link(self, link: MemoryLink) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO memory_links (
                link_id, player_id, episode_id_a, episode_id_b, link_type,
                strength, co_activation_count, created_at, last_activated_at, decay_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id, episode_id_a, episode_id_b, link_type) DO UPDATE SET
                link_id = excluded.link_id,
                strength = excluded.strength,
                co_activation_count = excluded.co_activation_count,
                created_at = excluded.created_at,
                last_activated_at = excluded.last_activated_at,
                decay_rate = excluded.decay_rate
            """,
            (
                link.link_id,
                link.player_id,
                link.episode_id_a,
                link.episode_id_b,
                link.link_type.value,
                link.strength,
                link.co_activation_count,
                _dt_to_iso(link.created_at),
                _dt_to_iso(link.last_activated_at),
                link.decay_rate,
            ),
        )
        self._conn.commit()

    def get_link(
        self,
        player_id: int,
        episode_id_a: str,
        episode_id_b: str,
        link_type: MemoryLinkType,
    ) -> MemoryLink | None:
        a, b = normalize_episode_pair(episode_id_a, episode_id_b)
        cur = self._conn.execute(
            """
            SELECT * FROM memory_links
            WHERE player_id = ? AND episode_id_a = ? AND episode_id_b = ? AND link_type = ?
            """,
            (player_id, a, b, link_type.value),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_link(row)

    def list_links_for_episode(
        self,
        player_id: int,
        episode_id: str,
        *,
        now: datetime,
        limit: int,
    ) -> list[MemoryLink]:
        if limit <= 0:
            return []
        eid = episode_id.strip()
        cur = self._conn.execute(
            """
            SELECT * FROM memory_links
            WHERE player_id = ? AND (episode_id_a = ? OR episode_id_b = ?)
            """,
            (player_id, eid, eid),
        )
        rows = cur.fetchall()
        links = [_row_to_link(r) for r in rows]
        links.sort(key=lambda ln: effective_link_strength(ln, now), reverse=True)
        return links[:limit]

    def list_all_incident_links(
        self,
        player_id: int,
        episode_id: str,
        *,
        now: datetime,
    ) -> list[MemoryLink]:
        _ = now
        eid = episode_id.strip()
        cur = self._conn.execute(
            """
            SELECT * FROM memory_links
            WHERE player_id = ? AND (episode_id_a = ? OR episode_id_b = ?)
            """,
            (player_id, eid, eid),
        )
        return [_row_to_link(r) for r in cur.fetchall()]

    def count_links_for_episode(self, player_id: int, episode_id: str) -> int:
        eid = episode_id.strip()
        cur = self._conn.execute(
            """
            SELECT COUNT(*) AS c FROM memory_links
            WHERE player_id = ? AND (episode_id_a = ? OR episode_id_b = ?)
            """,
            (player_id, eid, eid),
        )
        row = cur.fetchone()
        return int(row[0]) if row is not None else 0

    def remove_weakest_link_for_episode(
        self,
        player_id: int,
        episode_id: str,
        *,
        now: datetime,
    ) -> bool:
        cur = self._conn.execute(
            """
            SELECT * FROM memory_links
            WHERE player_id = ? AND (episode_id_a = ? OR episode_id_b = ?)
            """,
            (player_id, episode_id.strip(), episode_id.strip()),
        )
        rows = cur.fetchall()
        if not rows:
            return False
        weakest = min(rows, key=lambda r: effective_link_strength(_row_to_link(r), now))
        lid = str(weakest["link_id"])
        self._conn.execute("DELETE FROM memory_links WHERE link_id = ?", (lid,))
        self._conn.commit()
        return True

    def list_all_links_for_player(self, player_id: int) -> list[MemoryLink]:
        cur = self._conn.execute(
            "SELECT * FROM memory_links WHERE player_id = ?",
            (player_id,),
        )
        return [_row_to_link(r) for r in cur.fetchall()]


__all__ = ["SqliteMemoryLinkStore"]
