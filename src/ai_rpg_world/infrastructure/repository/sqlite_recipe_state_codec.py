"""Helpers for normalized recipe persistence."""

from __future__ import annotations

from ai_rpg_world.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.domain.item.value_object.recipe_ingredient import RecipeIngredient
from ai_rpg_world.domain.item.value_object.recipe_result import RecipeResult


def build_recipe(*, row: object, ingredient_rows: list[object]) -> RecipeAggregate:
    return RecipeAggregate(
        recipe_id=RecipeId(int(row["recipe_id"])),
        name=str(row["name"]),
        description=str(row["description"]),
        ingredients=[
            RecipeIngredient(
                item_spec_id=ItemSpecId(int(ingredient_row["ingredient_item_spec_id"])),
                quantity=int(ingredient_row["quantity"]),
            )
            for ingredient_row in ingredient_rows
        ],
        result=RecipeResult(
            item_spec_id=ItemSpecId(int(row["result_item_spec_id"])),
            quantity=int(row["result_quantity"]),
        ),
    )


__all__ = ["build_recipe"]
