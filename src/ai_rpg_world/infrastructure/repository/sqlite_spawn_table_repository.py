"""SQLite implementation of spawn table read repository and writer."""

from __future__ import annotations

import sqlite3
from typing import Optional

from ai_rpg_world.domain.monster.repository.spawn_table_repository import (
    SpawnTableRepository,
    SpawnTableWriter,
)
from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_monster_spawn_state_codec import (
    build_spawn_table,
    build_spawn_slot,
)


class SqliteSpawnTableRepository(SpawnTableRepository):
    """Read spot-based spawn tables from the game DB."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_connection(cls, connection: sqlite3.Connection) -> "SqliteSpawnTableRepository":
        return cls(connection)

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[SpotSpawnTable]:
        cur = self._conn.execute(
            "SELECT spot_id FROM game_spawn_tables WHERE spot_id = ?",
            (int(spot_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        slot_rows = self._conn.execute(
            """
            SELECT *
            FROM game_spawn_table_slots
            WHERE spot_id = ?
            ORDER BY slot_index ASC
            """,
            (int(spot_id),),
        ).fetchall()
        slots = []
        for slot_row in slot_rows:
            preferred_weather_rows = self._conn.execute(
                """
                SELECT weather_type
                FROM game_spawn_slot_preferred_weather
                WHERE spot_id = ? AND slot_index = ?
                ORDER BY weather_index ASC
                """,
                (int(spot_id), int(slot_row["slot_index"])),
            ).fetchall()
            required_trait_rows = self._conn.execute(
                """
                SELECT trait
                FROM game_spawn_slot_required_area_traits
                WHERE spot_id = ? AND slot_index = ?
                ORDER BY trait_index ASC
                """,
                (int(spot_id), int(slot_row["slot_index"])),
            ).fetchall()
            slots.append(
                build_spawn_slot(
                    spot_id=int(spot_id),
                    row=slot_row,
                    preferred_weather_rows=[row["weather_type"] for row in preferred_weather_rows],
                    required_trait_rows=[row["trait"] for row in required_trait_rows],
                )
            )
        return build_spawn_table(int(spot_id), slots)


class SqliteSpawnTableWriter(SpawnTableWriter):
    """SpawnTable 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteSpawnTableWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteSpawnTableWriter":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成した writer の書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    def replace_table(self, table: SpotSpawnTable) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_spawn_tables (spot_id)
            VALUES (?)
            ON CONFLICT(spot_id) DO NOTHING
            """,
            (int(table.spot_id),),
        )
        for table_name in (
            "game_spawn_table_slots",
            "game_spawn_slot_preferred_weather",
            "game_spawn_slot_required_area_traits",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE spot_id = ?", (int(table.spot_id),))
        self._conn.executemany(
            """
            INSERT INTO game_spawn_table_slots (
                spot_id, slot_index, x, y, z, template_id, weight, max_concurrent, time_band
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(table.spot_id),
                    index,
                    slot.coordinate.x,
                    slot.coordinate.y,
                    slot.coordinate.z,
                    int(slot.template_id),
                    slot.weight,
                    slot.max_concurrent,
                    None if slot.condition is None or slot.condition.time_band is None else slot.condition.time_band.value,
                )
                for index, slot in enumerate(table.slots)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_spawn_slot_preferred_weather (
                spot_id, slot_index, weather_index, weather_type
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (int(table.spot_id), slot_index, weather_index, weather_type.value)
                for slot_index, slot in enumerate(table.slots)
                if slot.condition is not None and slot.condition.preferred_weather is not None
                for weather_index, weather_type in enumerate(
                    sorted(slot.condition.preferred_weather, key=lambda value: value.value)
                )
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_spawn_slot_required_area_traits (
                spot_id, slot_index, trait_index, trait
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (int(table.spot_id), slot_index, trait_index, trait.value)
                for slot_index, slot in enumerate(table.slots)
                if slot.condition is not None and slot.condition.required_area_traits is not None
                for trait_index, trait in enumerate(
                    sorted(slot.condition.required_area_traits, key=lambda value: value.value)
                )
            ],
        )
        self._finalize_write()


__all__ = ["SqliteSpawnTableRepository", "SqliteSpawnTableWriter"]
