"""SQLite implementation of `SpotRepository` for the single game DB."""

from __future__ import annotations

import copy
import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)


class SqliteSpotRepository(SpotRepository):
    """Store spot metadata in normalized columns for query-heavy access."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        _commits_after_write: bool,
    ) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls,
        connection: sqlite3.Connection,
    ) -> "SqliteSpotRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
    ) -> "SqliteSpotRepository":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成したリポジトリの書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    @staticmethod
    def _row_to_spot(row: sqlite3.Row) -> Spot:
        parent_id = row["parent_id"]
        return Spot(
            spot_id=SpotId(int(row["spot_id"])),
            name=str(row["name"]),
            description=str(row["description"]),
            category=SpotCategoryEnum(str(row["category"])),
            parent_id=SpotId(int(parent_id)) if parent_id is not None else None,
        )

    def find_by_id(self, spot_id: SpotId) -> Optional[Spot]:
        cur = self._conn.execute(
            """
            SELECT spot_id, name, description, category, parent_id
            FROM game_spots
            WHERE spot_id = ?
            """,
            (int(spot_id),),
        )
        row = cur.fetchone()
        return None if row is None else copy.deepcopy(self._row_to_spot(row))

    def find_by_ids(self, spot_ids: List[SpotId]) -> List[Spot]:
        return [x for spot_id in spot_ids for x in [self.find_by_id(spot_id)] if x is not None]

    def save(self, spot: Spot) -> Spot:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_spots (spot_id, name, description, category, parent_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(spot_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                category = excluded.category,
                parent_id = excluded.parent_id
            """,
            (
                int(spot.spot_id),
                spot.name,
                spot.description,
                spot.category.value,
                int(spot.parent_id) if spot.parent_id is not None else None,
            ),
        )
        self._finalize_write()
        return copy.deepcopy(spot)

    def delete(self, spot_id: SpotId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_spots WHERE spot_id = ?",
            (int(spot_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[Spot]:
        cur = self._conn.execute(
            """
            SELECT spot_id, name, description, category, parent_id
            FROM game_spots
            ORDER BY spot_id ASC
            """
        )
        return [copy.deepcopy(self._row_to_spot(row)) for row in cur.fetchall()]

    def find_by_name(self, name: str) -> Optional[Spot]:
        if not name or not isinstance(name, str):
            return None
        key = name.strip()
        if not key:
            return None

        cur = self._conn.execute(
            """
            SELECT spot_id, name, description, category, parent_id
            FROM game_spots
            WHERE name = ?
            """,
            (key,),
        )
        row = cur.fetchone()
        return None if row is None else copy.deepcopy(self._row_to_spot(row))


__all__ = ["SqliteSpotRepository"]
