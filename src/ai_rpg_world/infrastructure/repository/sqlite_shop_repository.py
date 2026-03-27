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
from ai_rpg_world.infrastructure.repository.sqlite_shop_state_codec import build_shop


class SqliteShopRepository(ShopRepository):
    """Persist shop aggregates in normalized tables."""

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
        row = self._conn.execute("SELECT * FROM game_shops WHERE shop_id = ?", (int(entity_id),)).fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._build_shop_from_row(row))

    def find_by_ids(self, entity_ids: List[ShopId]) -> List[ShopAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[ShopAggregate]:
        rows = self._conn.execute("SELECT * FROM game_shops ORDER BY shop_id ASC").fetchall()
        return [copy.deepcopy(self._build_shop_from_row(row)) for row in rows]

    def save(self, entity: ShopAggregate) -> ShopAggregate:
        shop_id = int(entity.shop_id)
        self._conn.execute(
            """
            INSERT INTO game_shops (shop_id, spot_id, location_area_id, name, description)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(shop_id) DO UPDATE SET
                spot_id = excluded.spot_id,
                location_area_id = excluded.location_area_id,
                name = excluded.name,
                description = excluded.description
            """,
            (shop_id, int(entity.spot_id), int(entity.location_area_id), entity.name, entity.description),
        )
        self._conn.execute("DELETE FROM game_shop_owners WHERE shop_id = ?", (shop_id,))
        self._conn.execute("DELETE FROM game_shop_aggregate_listings WHERE shop_id = ?", (shop_id,))
        self._conn.executemany(
            "INSERT INTO game_shop_owners (shop_id, owner_id) VALUES (?, ?)",
            [(shop_id, int(owner_id)) for owner_id in sorted(entity.owner_ids, key=int)],
        )
        self._conn.executemany(
            """
            INSERT INTO game_shop_aggregate_listings (
                shop_id, listing_id, item_instance_id, price_per_unit, listed_by
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (shop_id, int(listing.listing_id), int(listing.item_instance_id), int(listing.price_per_unit), int(listing.listed_by))
                for listing in sorted(entity.listings.values(), key=lambda listing: int(listing.listing_id))
            ],
        )
        self._finalize_write()
        return entity

    def delete(self, entity_id: ShopId) -> bool:
        shop_id = int(entity_id)
        self._conn.execute("DELETE FROM game_shop_owners WHERE shop_id = ?", (shop_id,))
        self._conn.execute("DELETE FROM game_shop_aggregate_listings WHERE shop_id = ?", (shop_id,))
        cur = self._conn.execute("DELETE FROM game_shops WHERE shop_id = ?", (shop_id,))
        self._finalize_write()
        return cur.rowcount > 0

    def generate_shop_id(self) -> ShopId:
        return ShopId(allocate_sequence_value(self._conn, "shop_id", initial_value=0))

    def generate_listing_id(self) -> ShopListingId:
        return ShopListingId(allocate_sequence_value(self._conn, "shop_listing_id", initial_value=0))

    def find_by_spot_and_location(self, spot_id: SpotId, location_area_id: LocationAreaId) -> Optional[ShopAggregate]:
        row = self._conn.execute(
            "SELECT * FROM game_shops WHERE spot_id = ? AND location_area_id = ?",
            (int(spot_id), int(location_area_id)),
        ).fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._build_shop_from_row(row))

    def _build_shop_from_row(self, row: sqlite3.Row) -> ShopAggregate:
        shop_id = int(row["shop_id"])
        owner_rows = self._conn.execute("SELECT owner_id FROM game_shop_owners WHERE shop_id = ? ORDER BY owner_id ASC", (shop_id,)).fetchall()
        listing_rows = self._conn.execute(
            """
            SELECT listing_id, item_instance_id, price_per_unit, listed_by
            FROM game_shop_aggregate_listings
            WHERE shop_id = ?
            ORDER BY listing_id ASC
            """,
            (shop_id,),
        ).fetchall()
        return build_shop(row=row, owner_rows=list(owner_rows), listing_rows=list(listing_rows))


__all__ = ["SqliteShopRepository"]
