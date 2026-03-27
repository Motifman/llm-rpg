"""SQLite implementation of shop listing read model repository."""

from __future__ import annotations

import sqlite3
from typing import Any, List, Optional, Tuple

from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import ShopListingReadModel
from ai_rpg_world.domain.shop.repository.shop_listing_read_model_repository import (
    ShopListingReadModelRepository,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_state_codec import (
    shop_listing_row_to_model,
)


def _listing_tuple(entity: ShopListingReadModel) -> Tuple[Any, ...]:
    return (
        int(entity.listing_id),
        int(entity.shop_id),
        int(entity.item_instance_id),
        str(entity.item_name),
        int(entity.item_spec_id),
        int(entity.price_per_unit),
        int(entity.quantity),
        int(entity.listed_by),
        None if entity.listed_at is None else entity.listed_at.isoformat(),
    )


class SqliteShopListingReadModelRepository(ShopListingReadModelRepository):
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteShopListingReadModelRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteShopListingReadModelRepository":
        return cls(connection, _commits_after_write=False)

    def find_by_id(self, entity_id: ShopListingId) -> Optional[ShopListingReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM game_shop_listing_read_models WHERE listing_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        return shop_listing_row_to_model(row) if row else None

    def find_by_ids(self, entity_ids: List[ShopListingId]) -> List[ShopListingReadModel]:
        if not entity_ids:
            return []
        placeholders = ",".join("?" for _ in entity_ids)
        cur = self._conn.execute(
            f"SELECT * FROM game_shop_listing_read_models WHERE listing_id IN ({placeholders})",
            [int(entity_id) for entity_id in entity_ids],
        )
        return [shop_listing_row_to_model(row) for row in cur.fetchall()]

    def save(self, entity: ShopListingReadModel) -> ShopListingReadModel:
        self._conn.execute(
            """
            INSERT INTO game_shop_listing_read_models (
                listing_id, shop_id, item_instance_id, item_name, item_spec_id,
                price_per_unit, quantity, listed_by, listed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(listing_id) DO UPDATE SET
                shop_id = excluded.shop_id,
                item_instance_id = excluded.item_instance_id,
                item_name = excluded.item_name,
                item_spec_id = excluded.item_spec_id,
                price_per_unit = excluded.price_per_unit,
                quantity = excluded.quantity,
                listed_by = excluded.listed_by,
                listed_at = excluded.listed_at
            """,
            _listing_tuple(entity),
        )
        if self._commits_after_write:
            self._conn.commit()
        return entity

    def delete(self, entity_id: ShopListingId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM game_shop_listing_read_models WHERE listing_id = ?",
            (int(entity_id),),
        )
        if self._commits_after_write:
            self._conn.commit()
        return cur.rowcount > 0

    def find_all(self) -> List[ShopListingReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM game_shop_listing_read_models ORDER BY listing_id ASC"
        )
        return [shop_listing_row_to_model(row) for row in cur.fetchall()]

    def find_by_shop_id(self, shop_id: ShopId) -> List[ShopListingReadModel]:
        cur = self._conn.execute(
            """
            SELECT *
            FROM game_shop_listing_read_models
            WHERE shop_id = ?
            ORDER BY listing_id ASC
            """,
            (int(shop_id),),
        )
        return [shop_listing_row_to_model(row) for row in cur.fetchall()]


__all__ = ["SqliteShopListingReadModelRepository"]
