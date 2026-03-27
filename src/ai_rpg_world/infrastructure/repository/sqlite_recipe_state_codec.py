"""RecipeAggregate payload codec for SQLite repositories."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ai_rpg_world.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.domain.item.value_object.recipe_ingredient import RecipeIngredient
from ai_rpg_world.domain.item.value_object.recipe_result import RecipeResult


def recipe_to_payload(recipe: RecipeAggregate) -> Dict[str, Any]:
    return {
        "recipe_id": int(recipe.recipe_id),
        "name": recipe.name,
        "description": recipe.description,
        "ingredients": [
            {
                "item_spec_id": int(ingredient.item_spec_id),
                "quantity": int(ingredient.quantity),
            }
            for ingredient in recipe.ingredients
        ],
        "result": {
            "item_spec_id": int(recipe.result.item_spec_id),
            "quantity": int(recipe.result.quantity),
        },
    }


def payload_to_recipe(data: Dict[str, Any]) -> RecipeAggregate:
    ingredients: List[RecipeIngredient] = [
        RecipeIngredient(
            item_spec_id=ItemSpecId(int(ingredient["item_spec_id"])),
            quantity=int(ingredient["quantity"]),
        )
        for ingredient in data.get("ingredients", [])
    ]
    result_payload = data["result"]
    return RecipeAggregate(
        recipe_id=RecipeId(int(data["recipe_id"])),
        name=str(data["name"]),
        description=str(data["description"]),
        ingredients=ingredients,
        result=RecipeResult(
            item_spec_id=ItemSpecId(int(result_payload["item_spec_id"])),
            quantity=int(result_payload["quantity"]),
        ),
    )


def recipe_to_json(recipe: RecipeAggregate) -> str:
    return json.dumps(
        recipe_to_payload(recipe),
        ensure_ascii=True,
        separators=(",", ":"),
    )


def json_to_recipe(payload_json: str) -> RecipeAggregate:
    return payload_to_recipe(json.loads(payload_json))


__all__ = [
    "recipe_to_payload",
    "payload_to_recipe",
    "recipe_to_json",
    "json_to_recipe",
]
