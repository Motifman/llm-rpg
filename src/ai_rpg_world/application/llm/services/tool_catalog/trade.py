"""取引系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    TradeAcceptAvailabilityResolver,
    TradeCancelAvailabilityResolver,
    TradeDeclineAvailabilityResolver,
    TradeOfferAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_DECLINE,
    TOOL_NAME_TRADE_OFFER,
)

TRADE_OFFER_PARAMETERS = {
    "type": "object",
    "properties": {
        "inventory_item_label": {"type": "string", "description": "出品する在庫アイテムラベル（例: I1）。"},
        "requested_gold": {"type": "integer", "description": "希望価格（ゴールド）。"},
        "target_player_label": {
            "type": "string",
            "description": "宛先プレイヤーラベル（例: P1）。プロンプトの視界内対象から選択。省略時は誰でも受諾可能。",
        },
        "target_player_id": {
            "type": "integer",
            "description": "宛先プレイヤーID。target_player_label の代わりに使用可。",
            "default": None,
        },
    },
    "required": ["inventory_item_label", "requested_gold"],
}
TRADE_OFFER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_OFFER,
    description="アイテムを他プレイヤーに直接取引で出品します。",
    parameters=TRADE_OFFER_PARAMETERS,
)

TRADE_ACCEPT_PARAMETERS = {
    "type": "object",
    "properties": {
        "trade_label": {"type": "string", "description": "受諾する取引ラベル（例: T1）。"},
    },
    "required": ["trade_label"],
}
TRADE_ACCEPT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_ACCEPT,
    description="宛先の取引を受諾して購入します。",
    parameters=TRADE_ACCEPT_PARAMETERS,
)

TRADE_CANCEL_PARAMETERS = {
    "type": "object",
    "properties": {
        "trade_label": {"type": "string", "description": "キャンセルする取引ラベル（例: T1）。"},
    },
    "required": ["trade_label"],
}
TRADE_CANCEL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_CANCEL,
    description="自分が発信した取引をキャンセルします。",
    parameters=TRADE_CANCEL_PARAMETERS,
)

TRADE_DECLINE_PARAMETERS = {
    "type": "object",
    "properties": {
        "trade_label": {"type": "string", "description": "断る取引ラベル（例: T1）。直接取引の宛先のみ使用可能。"},
    },
    "required": ["trade_label"],
}
TRADE_DECLINE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_DECLINE,
    description="自分宛ての取引提案を断ります。直接取引の宛先のみ実行可能。",
    parameters=TRADE_DECLINE_PARAMETERS,
)


def get_trade_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """取引系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (TRADE_OFFER_DEFINITION, TradeOfferAvailabilityResolver()),
        (TRADE_ACCEPT_DEFINITION, TradeAcceptAvailabilityResolver()),
        (TRADE_CANCEL_DEFINITION, TradeCancelAvailabilityResolver()),
        (TRADE_DECLINE_DEFINITION, TradeDeclineAvailabilityResolver()),
    ]


__all__ = [
    "get_trade_specs",
]
