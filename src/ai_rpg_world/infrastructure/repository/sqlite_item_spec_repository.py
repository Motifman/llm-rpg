"""SQLite implementation of item spec read repository and writer."""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.repository.item_spec_repository import (
    ItemSpecRepository,
    ItemSpecWriter,
)
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_spec_state_codec import (
    build_item_spec,
    flatten_item_effect,
)


class SqliteItemSpecRepository(ItemSpecRepository):
    """Read item specs from the game DB."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_connection(cls, connection: sqlite3.Connection) -> "SqliteItemSpecRepository":
        return cls(connection)

    def _decode_row(self, row: sqlite3.Row | None) -> Optional[ItemSpec]:
        if row is None:
            return None
        effect_rows = self._conn.execute(
            """
            SELECT effect_id, parent_effect_id, effect_order, effect_kind, amount
            FROM game_item_spec_consume_effects
            WHERE item_spec_id = ?
            ORDER BY effect_id ASC
            """,
            (int(row["item_spec_id"]),),
        ).fetchall()
        return build_item_spec(row=row, effect_rows=effect_rows)

    def find_by_id(self, entity_id: ItemSpecId) -> Optional[ItemSpec]:
        cur = self._conn.execute(
            "SELECT * FROM game_item_specs WHERE item_spec_id = ?",
            (int(entity_id),),
        )
        return self._decode_row(cur.fetchone())

    def find_by_ids(self, entity_ids: List[ItemSpecId]) -> List[ItemSpec]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[ItemSpec]:
        cur = self._conn.execute("SELECT * FROM game_item_specs ORDER BY item_spec_id ASC")
        items: list[ItemSpec] = []
        for row in cur.fetchall():
            decoded = self._decode_row(row)
            if decoded is not None:
                items.append(decoded)
        return items

    def find_by_type(self, item_type: ItemType) -> List[ItemSpec]:
        cur = self._conn.execute(
            "SELECT * FROM game_item_specs WHERE item_type = ? ORDER BY item_spec_id ASC",
            (item_type.value,),
        )
        items: list[ItemSpec] = []
        for row in cur.fetchall():
            decoded = self._decode_row(row)
            if decoded is not None:
                items.append(decoded)
        return items

    def find_by_rarity(self, rarity: Rarity) -> List[ItemSpec]:
        cur = self._conn.execute(
            "SELECT * FROM game_item_specs WHERE rarity = ? ORDER BY item_spec_id ASC",
            (rarity.value,),
        )
        items: list[ItemSpec] = []
        for row in cur.fetchall():
            decoded = self._decode_row(row)
            if decoded is not None:
                items.append(decoded)
        return items

    def find_tradeable_items(self) -> List[ItemSpec]:
        cur = self._conn.execute(
            "SELECT * FROM game_item_specs WHERE is_tradeable = 1 ORDER BY item_spec_id ASC"
        )
        items: list[ItemSpec] = []
        for row in cur.fetchall():
            decoded = self._decode_row(row)
            if decoded is not None:
                items.append(decoded)
        return items

    def find_by_name(self, name: str) -> Optional[ItemSpec]:
        key = name.strip()
        if not key:
            return None
        cur = self._conn.execute(
            "SELECT * FROM game_item_specs WHERE name = ?",
            (key,),
        )
        return self._decode_row(cur.fetchone())

    def save(self, entity: ItemSpec) -> ItemSpec:
        raise NotImplementedError("SqliteItemSpecRepository is read-only. Use SqliteItemSpecWriter.")

    def delete(self, entity_id: ItemSpecId) -> bool:
        raise NotImplementedError("SqliteItemSpecRepository is read-only. Use SqliteItemSpecWriter.")


class SqliteItemSpecWriter(ItemSpecWriter):
    """ItemSpec 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteItemSpecWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteItemSpecWriter":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成した writer の書き込みは、アクティブなトランザクション内（with uow）で実行してください"
            )

    def replace_spec(self, item_spec: ItemSpec) -> None:
        self._assert_shared_transaction_active()
        item_spec_id = int(item_spec.item_spec_id)
        self._conn.execute(
            """
            INSERT INTO game_item_specs (
                item_spec_id, name, item_type, rarity, is_tradeable, description,
                max_stack_size, durability_max, equipment_type, is_placeable, placeable_object_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_spec_id) DO UPDATE SET
                name = excluded.name,
                item_type = excluded.item_type,
                rarity = excluded.rarity,
                is_tradeable = excluded.is_tradeable,
                description = excluded.description,
                max_stack_size = excluded.max_stack_size,
                durability_max = excluded.durability_max,
                equipment_type = excluded.equipment_type,
                is_placeable = excluded.is_placeable,
                placeable_object_type = excluded.placeable_object_type
            """,
            (
                item_spec_id,
                item_spec.name,
                item_spec.item_type.value,
                item_spec.rarity.value,
                0 if item_spec.item_type == ItemType.QUEST else 1,
                item_spec.description,
                int(item_spec.max_stack_size.value),
                item_spec.durability_max,
                None if item_spec.equipment_type is None else item_spec.equipment_type.value,
                1 if item_spec.is_placeable else 0,
                item_spec.placeable_object_type,
            ),
        )
        self._conn.execute("DELETE FROM game_item_spec_consume_effects WHERE item_spec_id = ?", (item_spec_id,))
        self._conn.executemany(
            """
            INSERT INTO game_item_spec_consume_effects (
                item_spec_id, effect_id, parent_effect_id, effect_order, effect_kind, amount
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (item_spec_id, effect_id, parent_id, effect_order, effect_kind, amount)
                for effect_id, parent_id, effect_order, effect_kind, amount in flatten_item_effect(item_spec.consume_effect)
            ],
        )
        self._finalize_write()

    def delete_spec(self, item_spec_id: ItemSpecId) -> bool:
        self._assert_shared_transaction_active()
        item_spec_id_value = int(item_spec_id)
        self._conn.execute("DELETE FROM game_item_spec_consume_effects WHERE item_spec_id = ?", (item_spec_id_value,))
        cur = self._conn.execute("DELETE FROM game_item_specs WHERE item_spec_id = ?", (item_spec_id_value,))
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteItemSpecRepository", "SqliteItemSpecWriter"]
