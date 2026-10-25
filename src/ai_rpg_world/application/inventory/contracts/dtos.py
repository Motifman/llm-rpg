from dataclasses import dataclass

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity


@dataclass(frozen=True)
class ItemSpecDto:
    """アイテムスペックDTO"""

    item_spec_id: int
    name: str
    item_type: ItemType
    rarity: Rarity
    description: str
    max_stack_size: int
    durability_max: int | None
    equipment_type: EquipmentType | None = None


@dataclass(frozen=True)
class ErrorResponseDto:
    """エラーレスポンスDTO"""

    error_code: str
    message: str
    details: str | None = None
    item_spec_id: int | None = None


@dataclass(frozen=True)
class RecipeIngredientDto:
    """レシピ材料DTO"""

    item_spec_id: int
    quantity: int


@dataclass(frozen=True)
class RecipeResultDto:
    """レシピ結果DTO"""

    item_spec_id: int
    quantity: int


@dataclass(frozen=True)
class RecipeDto:
    """レシピDTO"""

    recipe_id: int
    name: str
    description: str
    ingredients: list[RecipeIngredientDto]
    result: RecipeResultDto


@dataclass(frozen=True)
class ItemInfoQueryResultDto:
    """アイテム情報検索結果DTO（成功・失敗両方を含む）"""

    success: bool
    data: ItemSpecDto | None = None
    items: list[ItemSpecDto] | None = None
    error: ErrorResponseDto | None = None


@dataclass(frozen=True)
class RecipeInfoQueryResultDto:
    """レシピ情報検索結果DTO（成功・失敗両方を含む）"""

    success: bool
    data: RecipeDto | None = None
    recipes: list[RecipeDto] | None = None
    error: ErrorResponseDto | None = None


@dataclass(frozen=True)
class PlayerInventoryItemView:
    item_spec_id: int
    name: str
    description: str
    quantity: int


@dataclass(frozen=True)
class PlayerInventoryView:
    items: tuple[PlayerInventoryItemView, ...]
