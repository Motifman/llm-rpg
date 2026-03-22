"""取引系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    TradeAcceptTradePageAvailabilityResolver,
    TradeCancelTradePageAvailabilityResolver,
    TradeDeclineTradePageAvailabilityResolver,
    TradeEnterToolAvailabilityResolver,
    TradeExitToolAvailabilityResolver,
    TradeModeRequiredAvailabilityResolver,
    TradeOfferAvailabilityResolver,
    TradeVirtualPageMyTradesTabAvailabilityResolver,
    TradeVirtualPageNavigationAvailabilityResolver,
    TradeVirtualPagePagingAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_DECLINE,
    TOOL_NAME_TRADE_ENTER,
    TOOL_NAME_TRADE_EXIT,
    TOOL_NAME_TRADE_OFFER,
    TOOL_NAME_TRADE_OPEN_PAGE,
    TOOL_NAME_TRADE_PAGE_NEXT,
    TOOL_NAME_TRADE_PAGE_REFRESH,
    TOOL_NAME_TRADE_SWITCH_TAB,
    TOOL_NAME_TRADE_VIEW_CURRENT_PAGE,
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
        "trade_label": {"type": "string", "description": "受諾する取引ラベル（例: T1）。trade_ref とどちらか一方。"},
        "trade_ref": {
            "type": "string",
            "description": "現在のスナップショットの page-local ref（r_trade_*）。trade_label とどちらか一方。",
        },
    },
    "required": [],
}
TRADE_ACCEPT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_ACCEPT,
    description="宛先の取引を受諾して購入します。",
    parameters=TRADE_ACCEPT_PARAMETERS,
)

TRADE_CANCEL_PARAMETERS = {
    "type": "object",
    "properties": {
        "trade_label": {"type": "string", "description": "キャンセルする取引ラベル（例: T1）。trade_ref とどちらか一方。"},
        "trade_ref": {
            "type": "string",
            "description": "現在のスナップショットの page-local ref（r_trade_*）。",
        },
    },
    "required": [],
}
TRADE_CANCEL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_CANCEL,
    description="自分が発信した取引をキャンセルします。",
    parameters=TRADE_CANCEL_PARAMETERS,
)

TRADE_DECLINE_PARAMETERS = {
    "type": "object",
    "properties": {
        "trade_label": {"type": "string", "description": "断る取引ラベル（例: T1）。trade_ref とどちらか一方。"},
        "trade_ref": {
            "type": "string",
            "description": "現在のスナップショットの page-local ref（r_trade_*）。",
        },
    },
    "required": [],
}
TRADE_DECLINE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_DECLINE,
    description="自分宛ての取引提案を断ります。直接取引の宛先のみ実行可能。",
    parameters=TRADE_DECLINE_PARAMETERS,
)

TRADE_VIEW_CURRENT_PAGE_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
TRADE_VIEW_CURRENT_PAGE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_VIEW_CURRENT_PAGE,
    description="現在の仮想取引所画面のスナップショット（JSON）を返します。page-local trade_ref はこの結果に従います。",
    parameters=TRADE_VIEW_CURRENT_PAGE_PARAMETERS,
)

TRADE_OPEN_PAGE_PARAMETERS = {
    "type": "object",
    "properties": {
        "page": {
            "type": "string",
            "description": "遷移先: market, search, my_trades のいずれか。",
        },
        "my_trades_tab": {
            "type": "string",
            "description": "page が my_trades のとき: selling または incoming（省略時は selling）。",
        },
        "item_name": {"type": "string", "description": "page が search のとき: アイテム名の部分一致。"},
        "min_price": {"type": "integer", "description": "page が search のとき: 最低価格。"},
        "max_price": {"type": "integer", "description": "page が search のとき: 最高価格。"},
        "item_types": {"type": "array", "items": {"type": "string"}, "description": "page が search のとき: アイテム種別。"},
        "rarities": {"type": "array", "items": {"type": "string"}, "description": "page が search のとき: レアリティ。"},
        "equipment_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "page が search のとき: 装備種別。",
        },
    },
    "required": ["page"],
}
TRADE_OPEN_PAGE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_OPEN_PAGE,
    description="論理画面へ遷移します。search ではフィルタ引数を同時に指定できます。",
    parameters=TRADE_OPEN_PAGE_PARAMETERS,
)

TRADE_PAGE_NEXT_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
TRADE_PAGE_NEXT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_PAGE_NEXT,
    description="現在画面の次ページへ進みます（offset を limit 分進める）。",
    parameters=TRADE_PAGE_NEXT_PARAMETERS,
)

TRADE_PAGE_REFRESH_PARAMETERS = {
    "type": "object",
    "properties": {},
    "required": [],
}
TRADE_PAGE_REFRESH_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_PAGE_REFRESH,
    description="同一条件で画面を再取得します（ref の世代が更新されることがあります）。",
    parameters=TRADE_PAGE_REFRESH_PARAMETERS,
)

TRADE_SWITCH_TAB_PARAMETERS = {
    "type": "object",
    "properties": {
        "tab": {
            "type": "string",
            "description": "my_trades のタブ: selling または incoming。",
        },
    },
    "required": ["tab"],
}
TRADE_SWITCH_TAB_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TRADE_SWITCH_TAB,
    description="my_trades 画面で selling / incoming を切り替えます。",
    parameters=TRADE_SWITCH_TAB_PARAMETERS,
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
            TradeModeRequiredAvailabilityResolver(TradeAcceptTradePageAvailabilityResolver()),
        ),
        (
            TRADE_CANCEL_DEFINITION,
            TradeModeRequiredAvailabilityResolver(TradeCancelTradePageAvailabilityResolver()),
        ),
        (
            TRADE_DECLINE_DEFINITION,
            TradeModeRequiredAvailabilityResolver(TradeDeclineTradePageAvailabilityResolver()),
        ),
    ]


def get_trade_virtual_page_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """仮想取引所画面ナビゲーション用ツール（TradePageQueryService 配線時のみ登録）。"""
    nav = TradeVirtualPageNavigationAvailabilityResolver()
    paging = TradeVirtualPagePagingAvailabilityResolver()
    my_trades_tab = TradeVirtualPageMyTradesTabAvailabilityResolver()
    return [
        (TRADE_VIEW_CURRENT_PAGE_DEFINITION, nav),
        (TRADE_OPEN_PAGE_DEFINITION, nav),
        (TRADE_PAGE_NEXT_DEFINITION, paging),
        (TRADE_PAGE_REFRESH_DEFINITION, nav),
        (TRADE_SWITCH_TAB_DEFINITION, my_trades_tab),
    ]


__all__ = [
    "get_trade_specs",
    "get_trade_virtual_page_specs",
]
