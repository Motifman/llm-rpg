"""Reflection の実行境界を SQLite で永続化するポート実装"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from ai_rpg_world.application.llm.contracts.interfaces import IReflectionStatePort
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.llm.sqlite_memory_db import get_connection, init_schema


class SqliteReflectionStatePort(IReflectionStatePort):
    """Reflection 境界を SQLite で永続化。"""

    def __init__(self, db_path: Union[str, Path]) -> None:
        self._db_path = str(db_path)
        conn = get_connection(self._db_path)
        init_schema(conn)
        conn.close()

    def _conn(self):
        return get_connection(self._db_path)

    def get_last_reflection_game_day(self, player_id: PlayerId) -> Optional[int]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT last_game_day FROM reflection_state WHERE player_id = ?",
                (player_id.value,),
            )
            row = cur.fetchone()
            return int(row["last_game_day"]) if row else None
        finally:
            conn.close()

    def get_reflection_cursor(self, player_id: PlayerId) -> Optional[datetime]:
        conn = self._conn()
        try:
            cur = conn.execute(
                "SELECT last_cursor FROM reflection_state WHERE player_id = ?",
                (player_id.value,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return datetime.fromisoformat(row["last_cursor"])
        finally:
            conn.close()

    def mark_reflection_success(
        self, player_id: PlayerId, game_day: int, cursor: datetime
    ) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO reflection_state (player_id, last_game_day, last_cursor)
                   VALUES (?, ?, ?)
                   ON CONFLICT(player_id) DO UPDATE SET
                     last_game_day = excluded.last_game_day,
                     last_cursor = excluded.last_cursor""",
                (player_id.value, game_day, cursor.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
