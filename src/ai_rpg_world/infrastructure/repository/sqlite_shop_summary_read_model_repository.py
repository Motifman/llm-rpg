"""SQLite implementation of shop summary read model repository."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, List, Optional, Tuple

from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import ShopSummaryReadModel
from ai_rpg_world.domain.shop.repository.shop_summary_read_model_repository import (
    ShopSummaryReadModelRepository,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_state_codec import (
    shop_summary_row_to_model,
)


def _summary_tuple(entity: ShopSummaryReadModel) -> Tuple[Any, ...]:
    return (
        int(entity.shop_id),
        int(entity.spot_id),
        int(entity.location_area_id),
        str(entity.name),
        str(entity.description),
        json.dumps(list(entity.owner_ids), ensure_ascii=True, separators=(",", ":")),
        int(entity.listing_count),
        entity.created_at.isoformat(),
    )


class SqliteShopSummaryReadModelRepository(ShopSummaryReadModelRepository):
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteShopSummaryReadModelRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteShopSummaryReadModelRepository":
        return cls(connection, _commits_after_write=False)

    def find_by_id(self, entity_id: ShopId) -> Optional[ShopSummaryReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM game_shop_summary_read_models WHERE shop_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        return shop_summary_row_to_model(row) if row else None

    def find_by_ids(self, entity_ids: List[ShopId]) -> List[ShopSummaryReadModel]:
        if not entity_ids:
            return []
        placeholders = ",".join("?" for _ in entity_ids)
        cur = self._conn.execute(
            f"SELECT * FROM game_shop_summary_read_models WHERE shop_id IN ({placeholders})",
            [int(entity_id) for entity_id in entity_ids],
        )
        return [shop_summary_row_to_model(row) for row in cur.fetchall()]

    def save(self, entity: ShopSummaryReadModel) -> ShopSummaryReadModel:
        self._conn.execute(
            """
            INSERT INTO game_shop_summary_read_models (
                shop_id, spot_id, location_area_id, name, description,
                owner_ids_json, listing_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(shop_id) DO UPDATE SET
                spot_id = excluded.spot_id,
                location_area_id = excluded.location_area_id,
                name = excluded.name,
                description = excluded.description,
                owner_ids_json = excluded.owner_ids_json,
                listing_count = excluded.listing_count,
                created_at = excluded.created_at
            """,
            _summary_tuple(entity),
        )
        if self._commits_after_write:
            self._conn.commit()
        return entity

    def delete(self, entity_id: ShopId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM game_shop_summary_read_models WHERE shop_id = ?",
            (int(entity_id),),
        )
        if self._commits_after_write:
            self._conn.commit()
        return cur.rowcount > 0

    def find_all(self) -> List[ShopSummaryReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM game_shop_summary_read_models ORDER BY shop_id ASC"
        )
        return [shop_summary_row_to_model(row) for row in cur.fetchall()]

    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> Optional[ShopSummaryReadModel]:
        cur = self._conn.execute(
            """
            SELECT *
            FROM game_shop_summary_read_models
            WHERE spot_id = ? AND location_area_id = ?
            """,
            (int(spot_id), int(location_area_id)),
        )
        row = cur.fetchone()
        return shop_summary_row_to_model(row) if row else None

    def find_all_by_spot_id(self, spot_id: SpotId) -> List[ShopSummaryReadModel]:
        cur = self._conn.execute(
            """
            SELECT *
            FROM game_shop_summary_read_models
            WHERE spot_id = ?
            ORDER BY shop_id ASC
            """,
            (int(spot_id),),
        )
        return [shop_summary_row_to_model(row) for row in cur.fetchall()]


__all__ = ["SqliteShopSummaryReadModelRepository"]
