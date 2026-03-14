"""ショップ系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    ShopListItemAvailabilityResolver,
    ShopPurchaseAvailabilityResolver,
    ShopUnlistItemAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SHOP_LIST_ITEM,
    TOOL_NAME_SHOP_PURCHASE,
    TOOL_NAME_SHOP_UNLIST_ITEM,
)

SHOP_PURCHASE_PARAMETERS = {
    "type": "object",
    "properties": {
        "shop_label": {"type": "string", "description": "購入先ショップラベル（例: SH1）。"},
        "listing_label": {
            "type": "string",
            "description": "購入する出品ラベル（例: L1）。プロンプトの近隣ショップ出品一覧から選択。",
        },
        "listing_id": {"type": "integer", "description": "購入する出品のID。listing_label の代わりに使用可。"},
        "quantity": {"type": "integer", "description": "購入数量。", "default": 1},
    },
    "required": ["shop_label"],
}
SHOP_PURCHASE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SHOP_PURCHASE,
    description="ショップでアイテムを購入します。",
    parameters=SHOP_PURCHASE_PARAMETERS,
)

SHOP_LIST_ITEM_PARAMETERS = {
    "type": "object",
    "properties": {
        "shop_label": {"type": "string", "description": "出品先ショップラベル（例: SH1）。"},
        "inventory_item_label": {"type": "string", "description": "出品する在庫アイテムラベル（例: I1）。"},
        "price_per_unit": {"type": "integer", "description": "単価（ゴールド）。"},
    },
    "required": ["shop_label", "inventory_item_label", "price_per_unit"],
}
SHOP_LIST_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SHOP_LIST_ITEM,
    description="ショップにアイテムを出品します（オーナーのみ）。",
    parameters=SHOP_LIST_ITEM_PARAMETERS,
)

SHOP_UNLIST_ITEM_PARAMETERS = {
    "type": "object",
    "properties": {
        "shop_label": {"type": "string", "description": "取り下げ元ショップラベル（例: SH1）。"},
        "listing_label": {
            "type": "string",
            "description": "取り下げる出品ラベル（例: L1）。プロンプトの近隣ショップ出品一覧から選択。",
        },
        "listing_id": {"type": "integer", "description": "取り下げる出品のID。listing_label の代わりに使用可。"},
    },
    "required": ["shop_label"],
}
SHOP_UNLIST_ITEM_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SHOP_UNLIST_ITEM,
    description="ショップの出品を取り下げます（オーナーのみ）。",
    parameters=SHOP_UNLIST_ITEM_PARAMETERS,
)


def get_shop_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """ショップ系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (SHOP_PURCHASE_DEFINITION, ShopPurchaseAvailabilityResolver()),
        (SHOP_LIST_ITEM_DEFINITION, ShopListItemAvailabilityResolver()),
        (SHOP_UNLIST_ITEM_DEFINITION, ShopUnlistItemAvailabilityResolver()),
    ]


__all__ = [
    "get_shop_specs",
]
