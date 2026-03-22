"""取引系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    TradeAcceptAvailabilityResolver,
    TradeCancelAvailabilityResolver,
    TradeDeclineAvailabilityResolver,
    TradeEnterToolAvailabilityResolver,
    TradeExitToolAvailabilityResolver,
    TradeModeRequiredAvailabilityResolver,
    TradeOfferAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_DECLINE,
    TOOL_NAME_TRADE_ENTER,
    TOOL_NAME_TRADE_EXIT,
    TOOL_NAME_TRADE_OFFER,
)

TRADE_ENTER_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
TRADE_ENTER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_ENTER,
    description="ゲーム内の取引所アプリを開きます。開くと取引用ツールが利用可能になります。",
    parameters=TRADE_ENTER_PARAMETERS,
)

TRADE_EXIT_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
TRADE_EXIT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_EXIT,
    description="取引所アプリを閉じ、通常プレイに戻ります。",
    parameters=TRADE_EXIT_PARAMETERS,
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
    """取引系ツールの (definition, resolver) 一覧を返す。入場は未起動時、操作は取引所モード時のみ。"""
    return [
        (TRADE_ENTER_DEFINITION, TradeEnterToolAvailabilityResolver()),
        (TRADE_EXIT_DEFINITION, TradeExitToolAvailabilityResolver()),
        (
            TRADE_OFFER_DEFINITION,
            TradeModeRequiredAvailabilityResolver(TradeOfferAvailabilityResolver()),
        ),
        (
            TRADE_ACCEPT_DEFINITION,
            TradeModeRequiredAvailabilityResolver(TradeAcceptAvailabilityResolver()),
        ),
        (
            TRADE_CANCEL_DEFINITION,
            TradeModeRequiredAvailabilityResolver(TradeCancelAvailabilityResolver()),
        ),
        (
            TRADE_DECLINE_DEFINITION,
            TradeModeRequiredAvailabilityResolver(TradeDeclineAvailabilityResolver()),
        ),
    ]


__all__ = [
    "get_trade_specs",
]
