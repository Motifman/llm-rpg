"""Trade page session を LLM 向け JSON 文字列に変換する（Phase 3: メタのみ、Phase 4: rows 同梱）。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ai_rpg_world.application.trade.trade_virtual_pages.kinds import TradeVirtualPageKind
from ai_rpg_world.application.trade.trade_virtual_pages.trade_page_session_state import (
    TradePageSessionState,
)


def trade_page_base_snapshot_dict(state: TradePageSessionState) -> Dict[str, Any]:
    """page_kind / active_tab / filters / paging / snapshot_generation の辞書表現。"""
    active_tab: Any
    if state.page_kind == TradeVirtualPageKind.MY_TRADES:
        active_tab = state.my_trades_tab.value
    else:
        active_tab = None
    return {
        "page_kind": state.page_kind.value,
        "active_tab": active_tab,
        "filters": {
            "item_name": state.item_name,
            "min_price": state.min_price,
            "max_price": state.max_price,
            "item_types": list(state.item_types),
            "rarities": list(state.rarities),
            "equipment_types": list(state.equipment_types),
        },
        "paging": {"limit": state.limit, "offset": state.offset},
        "snapshot_generation": state.snapshot_generation,
    }


def trade_page_state_to_json(state: TradePageSessionState) -> str:
    """page_kind / active_tab / filters / paging / snapshot_generation を含むスナップショット JSON。"""
    return json.dumps(trade_page_base_snapshot_dict(state), ensure_ascii=False)


def trade_page_full_snapshot_json(
    state: TradePageSessionState,
    rows: List[Dict[str, Any]],
    next_cursor: Optional[str],
) -> str:
    """クエリ由来の行一覧と next_cursor を同梱したスナップショット JSON。"""
    payload = trade_page_base_snapshot_dict(state)
    payload["rows"] = rows
    paging = dict(payload["paging"])
    paging["next_cursor"] = next_cursor
    payload["paging"] = paging
    return json.dumps(payload, ensure_ascii=False)


__all__ = [
    "trade_page_base_snapshot_dict",
    "trade_page_state_to_json",
    "trade_page_full_snapshot_json",
]
