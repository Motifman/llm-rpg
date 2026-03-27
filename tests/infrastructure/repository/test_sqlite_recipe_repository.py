"""SQLite recipe repository tests."""

from __future__ import annotations

import sqlite3

import pytest

from ai_rpg_world.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.domain.item.value_object.recipe_ingredient import RecipeIngredient
from ai_rpg_world.domain.item.value_object.recipe_result import RecipeResult
from ai_rpg_world.infrastructure.repository.sqlite_recipe_repository import (
    SqliteRecipeRepository,
    SqliteRecipeWriter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _recipe(
    recipe_id: int,
    name: str,
    result_item_spec_id: int,
    ingredient_item_spec_ids: list[int],
) -> RecipeAggregate:
    return RecipeAggregate(
        recipe_id=RecipeId(recipe_id),
        name=name,
        description=f"{name} description",
        ingredients=[
            RecipeIngredient(item_spec_id=ItemSpecId(item_id), quantity=index + 1)
            for index, item_id in enumerate(ingredient_item_spec_ids)
        ],
        result=RecipeResult(item_spec_id=ItemSpecId(result_item_spec_id), quantity=1),
    )


@pytest.fixture
def sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


class TestSqliteRecipeRepository:
    def test_find_by_id_returns_none_when_empty(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        repo = SqliteRecipeRepository.for_connection(sqlite_conn)
        assert repo.find_by_id(RecipeId(1)) is None

    def test_writer_replace_and_find_roundtrip(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteRecipeWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteRecipeRepository.for_connection(sqlite_conn)
        writer.replace_recipe(_recipe(1, "鉄の剣の作成", 10, [1, 2]))

        loaded = repo.find_by_id(RecipeId(1))
        assert loaded is not None
        assert loaded.name == "鉄の剣の作成"
        assert loaded.result.item_spec_id == ItemSpecId(10)
        assert [ingredient.item_spec_id for ingredient in loaded.ingredients] == [
            ItemSpecId(1),
            ItemSpecId(2),
        ]

    def test_find_by_result_item_and_ingredient_use_indices(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteRecipeWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteRecipeRepository.for_connection(sqlite_conn)
        writer.replace_recipe(_recipe(1, "鉄の剣の作成", 10, [1, 2]))
        writer.replace_recipe(_recipe(2, "鋼の剣の作成", 11, [2, 3]))

        by_result = repo.find_by_result_item(ItemSpecId(11))
        by_ingredient = repo.find_by_ingredient(ItemSpecId(2))

        assert [recipe.recipe_id for recipe in by_result] == [RecipeId(2)]
        assert [recipe.recipe_id for recipe in by_ingredient] == [RecipeId(1), RecipeId(2)]

    def test_writer_replace_refreshes_ingredient_index(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteRecipeWriter.for_standalone_connection(sqlite_conn)
        repo = SqliteRecipeRepository.for_connection(sqlite_conn)
        writer.replace_recipe(_recipe(1, "鉄の剣の作成", 10, [1, 2]))
        writer.replace_recipe(_recipe(1, "鉄の剣の作成", 10, [3]))

        assert repo.find_by_ingredient(ItemSpecId(1)) == []
        assert [recipe.recipe_id for recipe in repo.find_by_ingredient(ItemSpecId(3))] == [
            RecipeId(1)
        ]

    def test_shared_writer_requires_active_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteRecipeWriter.for_shared_unit_of_work(sqlite_conn)
        with pytest.raises(RuntimeError, match="writer"):
            writer.replace_recipe(_recipe(1, "鉄の剣の作成", 10, [1, 2]))

    def test_shared_writer_delete_and_read_inside_transaction(
        self, sqlite_conn: sqlite3.Connection
    ) -> None:
        writer = SqliteRecipeWriter.for_standalone_connection(sqlite_conn)
        writer.replace_recipe(_recipe(1, "鉄の剣の作成", 10, [1, 2]))

        uow = SqliteUnitOfWork(connection=sqlite_conn)
        with uow:
            tx_writer = SqliteRecipeWriter.for_shared_unit_of_work(uow.connection)
            repo = SqliteRecipeRepository.for_connection(uow.connection)
            assert tx_writer.delete_recipe(RecipeId(1)) is True
            assert repo.find_by_id(RecipeId(1)) is None
