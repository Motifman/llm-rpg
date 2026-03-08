"""エピソード記憶ストアの SQLite 実装"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.contracts.interfaces import IEpisodeMemoryStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.llm.sqlite_memory_db import get_connection, init_schema


def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


class SqliteEpisodeMemoryStore(IEpisodeMemoryStore):
    """エピソード記憶の SQLite 永続化実装。"""

    def __init__(self, db_path: Union[str, Path]) -> None:
        self._db_path = str(db_path)
        conn = get_connection(self._db_path)
        init_schema(conn)
        conn.close()

    def _conn(self):
        return get_connection(self._db_path)

    def _row_to_entry(self, row, entities: tuple, world_objects: tuple, scope_keys: tuple) -> EpisodeMemoryEntry:
        ts = _parse_ts(row["timestamp"])
        return EpisodeMemoryEntry(
            id=row["id"],
            context_summary=row["context_summary"],
            action_taken=row["action_taken"],
            outcome_summary=row["outcome_summary"],
            entity_ids=entities,
            location_id=row["location_id"],
            timestamp=ts or datetime.now(),
            importance=row["importance"],
            surprise=bool(row["surprise"]),
            recall_count=row["recall_count"],
            world_object_ids=world_objects,
            spot_id_value=row["spot_id_value"],
            scope_keys=scope_keys,
        )

    def add(self, player_id: PlayerId, entry: EpisodeMemoryEntry) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entry, EpisodeMemoryEntry):
            raise TypeError("entry must be EpisodeMemoryEntry")
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO episode_memories
                   (id, player_id, context_summary, action_taken, outcome_summary,
                    location_id, timestamp, importance, surprise, recall_count,
                    spot_id_value)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.id,
                    player_id.value,
                    entry.context_summary,
                    entry.action_taken,
                    entry.outcome_summary,
                    entry.location_id,
                    entry.timestamp.isoformat(),
                    entry.importance,
                    1 if entry.surprise else 0,
                    entry.recall_count,
                    entry.spot_id_value,
                ),
            )
            for ent in entry.entity_ids:
                conn.execute(
                    "INSERT INTO episode_memory_entities (episode_id, entity_id) VALUES (?, ?)",
                    (entry.id, ent),
                )
            for wo in entry.world_object_ids:
                conn.execute(
                    "INSERT INTO episode_memory_world_objects (episode_id, world_object_id) VALUES (?, ?)",
                    (entry.id, wo),
                )
            for sk in entry.scope_keys:
                conn.execute(
                    "INSERT INTO episode_memory_scope_keys (episode_id, scope_key) VALUES (?, ?)",
                    (entry.id, sk),
                )
            conn.commit()
        finally:
            conn.close()

    def add_many(self, player_id: PlayerId, entries: List[EpisodeMemoryEntry]) -> None:
        for e in entries:
            self.add(player_id, e)

    def get_recent(
        self,
        player_id: PlayerId,
        limit: int,
        since: Optional[datetime] = None,
    ) -> List[EpisodeMemoryEntry]:
        conn = self._conn()
        try:
            sql = "SELECT * FROM episode_memories WHERE player_id = ?"
            params: list = [player_id.value]
            if since is not None:
                sql += " AND timestamp >= ?"
                params.append(since.isoformat())
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            result = []
            for row in rows:
                eid = row["id"]
                entities = tuple(
                    r[0] for r in conn.execute(
                        "SELECT entity_id FROM episode_memory_entities WHERE episode_id = ?",
                        (eid,),
                    ).fetchall()
                )
                world_objects = tuple(
                    r[0] for r in conn.execute(
                        "SELECT world_object_id FROM episode_memory_world_objects WHERE episode_id = ?",
                        (eid,),
                    ).fetchall()
                )
                scope_keys = tuple(
                    r[0] for r in conn.execute(
                        "SELECT scope_key FROM episode_memory_scope_keys WHERE episode_id = ?",
                        (eid,),
                    ).fetchall()
                )
                result.append(self._row_to_entry(dict(row), entities, world_objects, scope_keys))
            return result
        finally:
            conn.close()

    def find_by_entities_and_actions(
        self,
        player_id: PlayerId,
        entity_ids: Optional[List[str]] = None,
        action_names: Optional[List[str]] = None,
        world_object_ids: Optional[List[int]] = None,
        spot_ids: Optional[List[int]] = None,
        scope_keys: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[EpisodeMemoryEntry]:
        conn = self._conn()
        try:
            base = "SELECT * FROM episode_memories WHERE player_id = ?"
            params: list = [player_id.value]
            wo_sp_parts = []
            if world_object_ids:
                ph = ",".join("?" * len(world_object_ids))
                wo_sp_parts.append(f"""id IN (
                    SELECT episode_id FROM episode_memory_world_objects
                    WHERE world_object_id IN ({ph})
                )""")
                params.extend(world_object_ids)
            if spot_ids:
                ph = ",".join("?" * len(spot_ids))
                wo_sp_parts.append(f"spot_id_value IN ({ph})")
                params.extend(spot_ids)
            if wo_sp_parts:
                base += " AND (" + " OR ".join(wo_sp_parts) + ")"
            if scope_keys:
                placeholders = ",".join("?" * len(scope_keys))
                base += f""" AND id IN (
                    SELECT episode_id FROM episode_memory_scope_keys
                    WHERE scope_key IN ({placeholders})
                )"""
                params.extend(scope_keys)
            if entity_ids:
                placeholders = ",".join("?" * len(entity_ids))
                base += f""" AND (id IN (
                    SELECT episode_id FROM episode_memory_entities
                    WHERE entity_id IN ({placeholders})
                ) OR location_id IN ({placeholders}))"""
                params.extend(entity_ids)
                params.extend(entity_ids)
            if action_names:
                conditions = " OR ".join("action_taken LIKE ?" for _ in action_names)
                base += f" AND ({conditions})"
                for a in action_names:
                    params.append(f"%{a.lower()}%")
            base += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            cur = conn.execute(base, params)
            rows = cur.fetchall()
            result = []
            for row in rows:
                eid = row["id"]
                entities = tuple(
                    r[0] for r in conn.execute(
                        "SELECT entity_id FROM episode_memory_entities WHERE episode_id = ?",
                        (eid,),
                    ).fetchall()
                )
                world_objects = tuple(
                    r[0] for r in conn.execute(
                        "SELECT world_object_id FROM episode_memory_world_objects WHERE episode_id = ?",
                        (eid,),
                    ).fetchall()
                )
                scope_keys_tuple = tuple(
                    r[0] for r in conn.execute(
                        "SELECT scope_key FROM episode_memory_scope_keys WHERE episode_id = ?",
                        (eid,),
                    ).fetchall()
                )
                result.append(self._row_to_entry(dict(row), entities, world_objects, scope_keys_tuple))
            return result
        finally:
            conn.close()

    def increment_recall_count(self, player_id: PlayerId, episode_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE episode_memories SET recall_count = recall_count + 1 WHERE id = ? AND player_id = ?",
                (episode_id, player_id.value),
            )
            conn.commit()
        finally:
            conn.close()

    def get_important_or_high_recall(
        self,
        player_id: PlayerId,
        since: datetime,
        min_importance: Optional[str] = None,
        min_recall_count: Optional[int] = None,
        limit: int = 20,
    ) -> List[EpisodeMemoryEntry]:
        conn = self._conn()
        try:
            sql = "SELECT * FROM episode_memories WHERE player_id = ? AND timestamp >= ?"
            params: list = [player_id.value, since.isoformat()]
            if min_importance:
                order = ("low", "medium", "high")
                if min_importance not in order:
                    raise ValueError(f"min_importance must be 'low', 'medium', or 'high', got: {min_importance!r}")
                min_idx = order.index(min_importance)
                sql += f" AND CASE importance WHEN 'low' THEN 0 WHEN 'medium' THEN 1 WHEN 'high' THEN 2 ELSE -1 END >= ?"
                params.append(min_idx)
            if min_recall_count is not None:
                sql += " AND recall_count >= ?"
                params.append(min_recall_count)
            sql += " ORDER BY recall_count DESC, timestamp DESC LIMIT ?"
            params.append(limit)
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            result = []
            for row in rows:
                eid = row["id"]
                entities = tuple(
                    r[0] for r in conn.execute(
                        "SELECT entity_id FROM episode_memory_entities WHERE episode_id = ?",
                        (eid,),
                    ).fetchall()
                )
                world_objects = tuple(
                    r[0] for r in conn.execute(
                        "SELECT world_object_id FROM episode_memory_world_objects WHERE episode_id = ?",
                        (eid,),
                    ).fetchall()
                )
                scope_keys_tuple = tuple(
                    r[0] for r in conn.execute(
                        "SELECT scope_key FROM episode_memory_scope_keys WHERE episode_id = ?",
                        (eid,),
                    ).fetchall()
                )
                result.append(self._row_to_entry(dict(row), entities, world_objects, scope_keys_tuple))
            return result
        finally:
            conn.close()
