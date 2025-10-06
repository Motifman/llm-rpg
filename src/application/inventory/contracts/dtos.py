from dataclasses import dataclass
from typing import Optional
from src.domain.item.enum.item_enum import ItemType, Rarity


@dataclass(frozen=True)
class ItemSpecDto:
    """アイテムスペックDTO"""
    item_spec_id: int
    name: str
    item_type: ItemType
    rarity: Rarity
    description: str
    max_stack_size: int
    durability_max: Optional[int]


@dataclass(frozen=True)
class ErrorResponseDto:
    """エラーレスポンスDTO"""
    error_code: str
    message: str
    details: Optional[str] = None
    item_spec_id: Optional[int] = None


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
    data: Optional[ItemSpecDto] = None
    items: Optional[list[ItemSpecDto]] = None
    error: Optional[ErrorResponseDto] = None


@dataclass(frozen=True)
class RecipeInfoQueryResultDto:
    """レシピ情報検索結果DTO（成功・失敗両方を含む）"""
    success: bool
    data: Optional[RecipeDto] = None
    recipes: Optional[list[RecipeDto]] = None
    error: Optional[ErrorResponseDto] = None
