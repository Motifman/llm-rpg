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
    item_spec_to_json,
    json_to_item_spec,
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
        return json_to_item_spec(str(row["payload_json"]))

    def find_by_id(self, entity_id: ItemSpecId) -> Optional[ItemSpec]:
        cur = self._conn.execute(
            "SELECT payload_json FROM game_item_specs WHERE item_spec_id = ?",
            (int(entity_id),),
        )
        return self._decode_row(cur.fetchone())

    def find_by_ids(self, entity_ids: List[ItemSpecId]) -> List[ItemSpec]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[ItemSpec]:
        cur = self._conn.execute(
            "SELECT payload_json FROM game_item_specs ORDER BY item_spec_id ASC"
        )
        return [json_to_item_spec(str(row["payload_json"])) for row in cur.fetchall()]

    def find_by_type(self, item_type: ItemType) -> List[ItemSpec]:
        cur = self._conn.execute(
            """
            SELECT payload_json
            FROM game_item_specs
            WHERE item_type = ?
            ORDER BY item_spec_id ASC
            """,
            (item_type.value,),
        )
        return [json_to_item_spec(str(row["payload_json"])) for row in cur.fetchall()]

    def find_by_rarity(self, rarity: Rarity) -> List[ItemSpec]:
        cur = self._conn.execute(
            """
            SELECT payload_json
            FROM game_item_specs
            WHERE rarity = ?
            ORDER BY item_spec_id ASC
            """,
            (rarity.value,),
        )
        return [json_to_item_spec(str(row["payload_json"])) for row in cur.fetchall()]

    def find_tradeable_items(self) -> List[ItemSpec]:
        cur = self._conn.execute(
            """
            SELECT payload_json
            FROM game_item_specs
            WHERE is_tradeable = 1
            ORDER BY item_spec_id ASC
            """
        )
        return [json_to_item_spec(str(row["payload_json"])) for row in cur.fetchall()]

    def find_by_name(self, name: str) -> Optional[ItemSpec]:
        key = name.strip()
        if not key:
            return None
        cur = self._conn.execute(
            "SELECT payload_json FROM game_item_specs WHERE name = ?",
            (key,),
        )
        return self._decode_row(cur.fetchone())

    def save(self, entity: ItemSpec) -> ItemSpec:
        raise NotImplementedError(
            "SqliteItemSpecRepository is read-only. Use SqliteItemSpecWriter."
        )

    def delete(self, entity_id: ItemSpecId) -> bool:
        raise NotImplementedError(
            "SqliteItemSpecRepository is read-only. Use SqliteItemSpecWriter."
        )


class SqliteItemSpecWriter(ItemSpecWriter):
    """ItemSpec 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteItemSpecWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteItemSpecWriter":
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

    def replace_spec(self, item_spec: ItemSpec) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_item_specs (
                item_spec_id,
                name,
                item_type,
                rarity,
                is_tradeable,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_spec_id) DO UPDATE SET
                name = excluded.name,
                item_type = excluded.item_type,
                rarity = excluded.rarity,
                is_tradeable = excluded.is_tradeable,
                payload_json = excluded.payload_json
            """,
            (
                int(item_spec.item_spec_id),
                item_spec.name,
                item_spec.item_type.value,
                item_spec.rarity.value,
                0 if item_spec.item_type == ItemType.QUEST else 1,
                item_spec_to_json(item_spec),
            ),
        )
        self._finalize_write()

    def delete_spec(self, item_spec_id: ItemSpecId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_item_specs WHERE item_spec_id = ?",
            (int(item_spec_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteItemSpecRepository", "SqliteItemSpecWriter"]
