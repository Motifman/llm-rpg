"""SQLite implementation of shop aggregate repository."""

from __future__ import annotations

import copy
import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_state_codec import (
    json_to_shop,
    shop_to_json,
)


class SqliteShopRepository(ShopRepository):
    """Persist shop aggregates in the single game DB."""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteShopRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteShopRepository":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def find_by_id(self, entity_id: ShopId) -> Optional[ShopAggregate]:
        cur = self._conn.execute(
            "SELECT payload_json FROM game_shops WHERE shop_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(json_to_shop(str(row["payload_json"])))

    def find_by_ids(self, entity_ids: List[ShopId]) -> List[ShopAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[ShopAggregate]:
        cur = self._conn.execute(
            "SELECT payload_json FROM game_shops ORDER BY shop_id ASC"
        )
        return [copy.deepcopy(json_to_shop(str(row["payload_json"]))) for row in cur.fetchall()]

    def save(self, entity: ShopAggregate) -> ShopAggregate:
        self._conn.execute(
            """
            INSERT INTO game_shops (
                shop_id,
                spot_id,
                location_area_id,
                name,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(shop_id) DO UPDATE SET
                spot_id = excluded.spot_id,
                location_area_id = excluded.location_area_id,
                name = excluded.name,
                payload_json = excluded.payload_json
            """,
            (
                int(entity.shop_id),
                int(entity.spot_id),
                int(entity.location_area_id),
                entity.name,
                shop_to_json(entity),
            ),
        )
        self._finalize_write()
        return entity

    def delete(self, entity_id: ShopId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM game_shops WHERE shop_id = ?",
            (int(entity_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def generate_shop_id(self) -> ShopId:
        return ShopId(allocate_sequence_value(self._conn, "shop_id", initial_value=0))

    def generate_listing_id(self) -> ShopListingId:
        return ShopListingId(
            allocate_sequence_value(self._conn, "shop_listing_id", initial_value=0)
        )

    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> Optional[ShopAggregate]:
        cur = self._conn.execute(
            """
            SELECT payload_json
            FROM game_shops
            WHERE spot_id = ? AND location_area_id = ?
            """,
            (int(spot_id), int(location_area_id)),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(json_to_shop(str(row["payload_json"])))


__all__ = ["SqliteShopRepository"]
