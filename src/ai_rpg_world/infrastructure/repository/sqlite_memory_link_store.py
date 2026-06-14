"""MemoryLinkRepository の SQLite 実装（主観エピソード DB と同一ファイル）。

Phase 3 Step 3c-3 (Issue #470): legacy player_id 版を撤去し、being_id 版のみ
を残した。schema v5 で legacy ``memory_links`` テーブルも DROP される。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
    effective_link_strength,
    normalize_episode_pair,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    MemoryLinkRepository,
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


class SqliteMemoryLinkStore(MemoryLinkRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        apply_memory_graph_migrations(connection)

    def upsert_link_by_being(self, being_id: BeingId, link: MemoryLink) -> None:
        """being_id keyed で link を upsert する。

        PK は (being_id_value, episode_id_a, episode_id_b, link_type)。link_id は
        非 PK で、UPSERT 時に最新値で上書きされる。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(link, MemoryLink):
            raise TypeError("link must be MemoryLink")
        self._conn.execute(
            """
            INSERT INTO memory_links_by_being (
                link_id, being_id_value, episode_id_a, episode_id_b, link_type,
                strength, co_activation_count, created_at, last_activated_at,
                decay_rate, player_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(being_id_value, episode_id_a, episode_id_b, link_type) DO UPDATE SET
                link_id = excluded.link_id,
                strength = excluded.strength,
                co_activation_count = excluded.co_activation_count,
                created_at = excluded.created_at,
                last_activated_at = excluded.last_activated_at,
                decay_rate = excluded.decay_rate,
                player_id = excluded.player_id
            """,
            (
                link.link_id,
                being_id.value,
                link.episode_id_a,
                link.episode_id_b,
                link.link_type.value,
                link.strength,
                link.co_activation_count,
                _dt_to_iso(link.created_at),
                _dt_to_iso(link.last_activated_at),
                link.decay_rate,
                link.player_id,
            ),
        )
        self._conn.commit()

    def get_link_by_being(
        self,
        being_id: BeingId,
        episode_id_a: str,
        episode_id_b: str,
        link_type: MemoryLinkType,
    ) -> MemoryLink | None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        a, b = normalize_episode_pair(episode_id_a, episode_id_b)
        cur = self._conn.execute(
            """
            SELECT * FROM memory_links_by_being
            WHERE being_id_value = ? AND episode_id_a = ?
              AND episode_id_b = ? AND link_type = ?
            """,
            (being_id.value, a, b, link_type.value),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_link(row)

    def list_links_for_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
        *,
        now: datetime,
        limit: int,
    ) -> list[MemoryLink]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if limit <= 0:
            return []
        eid = episode_id.strip()
        cur = self._conn.execute(
            """
            SELECT * FROM memory_links_by_being
            WHERE being_id_value = ? AND (episode_id_a = ? OR episode_id_b = ?)
            """,
            (being_id.value, eid, eid),
        )
        rows = cur.fetchall()
        links = [_row_to_link(r) for r in rows]
        links.sort(key=lambda ln: effective_link_strength(ln, now), reverse=True)
        return links[:limit]

    def list_all_incident_links_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
        *,
        now: datetime,
    ) -> list[MemoryLink]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        _ = now
        eid = episode_id.strip()
        cur = self._conn.execute(
            """
            SELECT * FROM memory_links_by_being
            WHERE being_id_value = ? AND (episode_id_a = ? OR episode_id_b = ?)
            """,
            (being_id.value, eid, eid),
        )
        return [_row_to_link(r) for r in cur.fetchall()]

    def count_links_for_episode_by_being(
        self, being_id: BeingId, episode_id: str
    ) -> int:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        eid = episode_id.strip()
        # MemoryLink VO の `__post_init__` で a < b に正規化されるため、
        # 同一行が `episode_id_a = ?` と `episode_id_b = ?` の両方を満たす
        # ことはなく、OR で COUNT しても二重カウントにならない。
        cur = self._conn.execute(
            """
            SELECT COUNT(*) AS c FROM memory_links_by_being
            WHERE being_id_value = ? AND (episode_id_a = ? OR episode_id_b = ?)
            """,
            (being_id.value, eid, eid),
        )
        row = cur.fetchone()
        return int(row[0]) if row is not None else 0

    def remove_weakest_link_for_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
        *,
        now: datetime,
    ) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        eid = episode_id.strip()
        cur = self._conn.execute(
            """
            SELECT * FROM memory_links_by_being
            WHERE being_id_value = ? AND (episode_id_a = ? OR episode_id_b = ?)
            """,
            (being_id.value, eid, eid),
        )
        rows = cur.fetchall()
        if not rows:
            return False
        weakest = min(rows, key=lambda r: effective_link_strength(_row_to_link(r), now))
        # 一意性は PK の 4 列組 (being_id_value, episode_id_a, episode_id_b,
        # link_type) で確保されている。link_id は本テーブルでは非 PK (= UPSERT
        # 時の更新可能フィールド) で複数 PK 組に同じ link_id が紐づきうるため、
        # PK 4 列組で DELETE する。
        self._conn.execute(
            """
            DELETE FROM memory_links_by_being
            WHERE being_id_value = ? AND episode_id_a = ?
              AND episode_id_b = ? AND link_type = ?
            """,
            (
                being_id.value,
                str(weakest["episode_id_a"]),
                str(weakest["episode_id_b"]),
                str(weakest["link_type"]),
            ),
        )
        self._conn.commit()
        return True

    def list_all_links_for_being(self, being_id: BeingId) -> list[MemoryLink]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        cur = self._conn.execute(
            "SELECT * FROM memory_links_by_being WHERE being_id_value = ?",
            (being_id.value,),
        )
        return [_row_to_link(r) for r in cur.fetchall()]


    def replace_all_by_being(
        self, being_id: BeingId, links: list[MemoryLink]
    ) -> None:
        """being_id 配下のリンクを single transaction で完全置換する。

        Phase 4 Step 4-2a: snapshot restore primitive。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(links, list):
            raise TypeError("links must be list")
        for ln in links:
            if not isinstance(ln, MemoryLink):
                raise TypeError("links elements must be MemoryLink")
        # 注意: 明示的 BEGIN を打たない理由は sqlite_semantic_memory_store.py の
        # ``replace_all_by_being`` 同コメント参照 (implicit transaction との衝突回避)。
        try:
            self._conn.execute(
                "DELETE FROM memory_links_by_being WHERE being_id_value = ?",
                (being_id.value,),
            )
            for link in links:
                self._conn.execute(
                    """
                    INSERT INTO memory_links_by_being (
                        link_id, being_id_value, episode_id_a, episode_id_b, link_type,
                        strength, co_activation_count, created_at, last_activated_at,
                        decay_rate, player_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        link.link_id,
                        being_id.value,
                        link.episode_id_a,
                        link.episode_id_b,
                        link.link_type.value,
                        link.strength,
                        link.co_activation_count,
                        _dt_to_iso(link.created_at),
                        _dt_to_iso(link.last_activated_at),
                        link.decay_rate,
                        link.player_id,
                    ),
                )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise


__all__ = ["SqliteMemoryLinkStore"]
