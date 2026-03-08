"""長期記憶ストアの SQLite 実装"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from ai_rpg_world.application.llm.contracts.dtos import LongTermFactEntry, MemoryLawEntry
from ai_rpg_world.application.llm.contracts.interfaces import ILongTermMemoryStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.llm.sqlite_memory_db import get_connection, init_schema


class SqliteLongTermMemoryStore(ILongTermMemoryStore):
    """事実・教訓と法則を SQLite で永続化する実装。"""

    def __init__(self, db_path: Union[str, Path]) -> None:
        self._db_path = str(db_path)
        conn = get_connection(self._db_path)
        init_schema(conn)
        conn.close()

    def _conn(self):
        return get_connection(self._db_path)

    def add_fact(self, player_id: PlayerId, content: str) -> str:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(content, str):
            raise TypeError("content must be str")
        fact_id = str(uuid.uuid4())
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO long_term_facts (id, player_id, content, updated_at) VALUES (?, ?, ?, ?)",
                (fact_id, player_id.value, content, datetime.now().isoformat()),
            )
            conn.commit()
            return fact_id
        finally:
            conn.close()

    def search_facts(
        self,
        player_id: PlayerId,
        keywords: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[LongTermFactEntry]:
        conn = self._conn()
        try:
            sql = "SELECT * FROM long_term_facts WHERE player_id = ?"
            params: list = [player_id.value]
            if keywords:
                conds = " OR ".join("content LIKE ?" for _ in keywords)
                sql += f" AND ({conds})"
                for k in keywords:
                    params.append(f"%{k}%")
            sql += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            return [
                LongTermFactEntry(
                    id=row["id"],
                    content=row["content"],
                    player_id=row["player_id"],
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def upsert_law(
        self,
        player_id: PlayerId,
        subject: str,
        relation: str,
        target: str,
        delta_strength: float = 1.0,
    ) -> None:
        conn = self._conn()
        try:
            cur = conn.execute(
                """SELECT id, strength FROM memory_laws
                   WHERE player_id = ? AND subject = ? AND relation = ? AND target = ?""",
                (player_id.value, subject, relation, target),
            )
            row = cur.fetchone()
            if row:
                new_strength = max(0.0, row["strength"] + delta_strength)
                conn.execute(
                    "UPDATE memory_laws SET strength = ? WHERE id = ?",
                    (new_strength, row["id"]),
                )
            else:
                law_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO memory_laws (id, player_id, subject, relation, target, strength)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (law_id, player_id.value, subject, relation, target, max(0.0, delta_strength)),
                )
            conn.commit()
        finally:
            conn.close()

    def find_laws(
        self,
        player_id: PlayerId,
        subject: Optional[str] = None,
        action_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[MemoryLawEntry]:
        conn = self._conn()
        try:
            sql = "SELECT * FROM memory_laws WHERE player_id = ?"
            params: list = [player_id.value]
            if subject:
                sql += " AND subject LIKE ?"
                params.append(f"%{subject}%")
            if action_name:
                sql += " AND (relation LIKE ? OR subject LIKE ?)"
                params.append(f"%{action_name}%")
                params.append(f"%{action_name}%")
            sql += " ORDER BY strength DESC LIMIT ?"
            params.append(limit)
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            return [
                MemoryLawEntry(
                    id=row["id"],
                    subject=row["subject"],
                    relation=row["relation"],
                    target=row["target"],
                    strength=row["strength"],
                    player_id=row["player_id"],
                )
                for row in rows
            ]
        finally:
            conn.close()
