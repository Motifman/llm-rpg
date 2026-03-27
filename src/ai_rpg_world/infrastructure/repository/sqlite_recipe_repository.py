"""SQLite implementation of recipe read repository and writer."""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from ai_rpg_world.domain.item.repository.recipe_repository import (
    RecipeRepository,
    RecipeWriter,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_recipe_state_codec import (
    json_to_recipe,
    recipe_to_json,
)


class SqliteRecipeRepository(RecipeRepository):
    """Read recipes from the game DB."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_connection(cls, connection: sqlite3.Connection) -> "SqliteRecipeRepository":
        return cls(connection)

    def _decode_row(self, row: sqlite3.Row | None) -> Optional[RecipeAggregate]:
        if row is None:
            return None
        return json_to_recipe(str(row["payload_json"]))

    def find_by_id(self, entity_id: RecipeId) -> Optional[RecipeAggregate]:
        cur = self._conn.execute(
            "SELECT payload_json FROM game_recipes WHERE recipe_id = ?",
            (int(entity_id),),
        )
        return self._decode_row(cur.fetchone())

    def find_by_ids(self, entity_ids: List[RecipeId]) -> List[RecipeAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[RecipeAggregate]:
        cur = self._conn.execute(
            "SELECT payload_json FROM game_recipes ORDER BY recipe_id ASC"
        )
        return [json_to_recipe(str(row["payload_json"])) for row in cur.fetchall()]

    def find_by_result_item(self, item_spec_id: ItemSpecId) -> List[RecipeAggregate]:
        cur = self._conn.execute(
            """
            SELECT payload_json
            FROM game_recipes
            WHERE result_item_spec_id = ?
            ORDER BY recipe_id ASC
            """,
            (int(item_spec_id),),
        )
        return [json_to_recipe(str(row["payload_json"])) for row in cur.fetchall()]

    def find_by_ingredient(self, item_spec_id: ItemSpecId) -> List[RecipeAggregate]:
        cur = self._conn.execute(
            """
            SELECT DISTINCT recipe.payload_json
            FROM game_recipe_ingredients ingredient
            JOIN game_recipes recipe ON recipe.recipe_id = ingredient.recipe_id
            WHERE ingredient.ingredient_item_spec_id = ?
            ORDER BY recipe.recipe_id ASC
            """,
            (int(item_spec_id),),
        )
        return [json_to_recipe(str(row["payload_json"])) for row in cur.fetchall()]

    def save(self, entity: RecipeAggregate) -> RecipeAggregate:
        raise NotImplementedError(
            "SqliteRecipeRepository is read-only. Use SqliteRecipeWriter."
        )

    def delete(self, entity_id: RecipeId) -> bool:
        raise NotImplementedError(
            "SqliteRecipeRepository is read-only. Use SqliteRecipeWriter."
        )


class SqliteRecipeWriter(RecipeWriter):
    """Recipe 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteRecipeWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteRecipeWriter":
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

    def replace_recipe(self, recipe: RecipeAggregate) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_recipes (recipe_id, name, result_item_spec_id, payload_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(recipe_id) DO UPDATE SET
                name = excluded.name,
                result_item_spec_id = excluded.result_item_spec_id,
                payload_json = excluded.payload_json
            """,
            (
                int(recipe.recipe_id),
                recipe.name,
                int(recipe.result.item_spec_id),
                recipe_to_json(recipe),
            ),
        )
        self._conn.execute(
            "DELETE FROM game_recipe_ingredients WHERE recipe_id = ?",
            (int(recipe.recipe_id),),
        )
        self._conn.executemany(
            """
            INSERT INTO game_recipe_ingredients (
                recipe_id,
                ingredient_item_spec_id,
                quantity
            )
            VALUES (?, ?, ?)
            """,
            [
                (
                    int(recipe.recipe_id),
                    int(ingredient.item_spec_id),
                    int(ingredient.quantity),
                )
                for ingredient in recipe.ingredients
            ],
        )
        self._finalize_write()

    def delete_recipe(self, recipe_id: RecipeId) -> bool:
        self._assert_shared_transaction_active()
        self._conn.execute(
            "DELETE FROM game_recipe_ingredients WHERE recipe_id = ?",
            (int(recipe_id),),
        )
        cur = self._conn.execute(
            "DELETE FROM game_recipes WHERE recipe_id = ?",
            (int(recipe_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteRecipeRepository", "SqliteRecipeWriter"]
