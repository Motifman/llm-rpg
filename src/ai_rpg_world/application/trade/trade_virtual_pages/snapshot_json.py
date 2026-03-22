"""Trade page session を LLM 向け JSON 文字列に変換する（Phase 3: セッション由来の最小メタのみ）。"""

from __future__ import annotations

import json
from typing import Any, Dict

from ai_rpg_world.application.trade.trade_virtual_pages.kinds import TradeVirtualPageKind
from ai_rpg_world.application.trade.trade_virtual_pages.trade_page_session_state import (
    TradePageSessionState,
)


def trade_page_state_to_json(state: TradePageSessionState) -> str:
    """page_kind / active_tab / filters / paging / snapshot_generation を含むスナップショット JSON。"""
    active_tab: Any
    if state.page_kind == TradeVirtualPageKind.MY_TRADES:
        active_tab = state.my_trades_tab.value
    else:
        active_tab = None
    payload: Dict[str, Any] = {
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
    return json.dumps(payload, ensure_ascii=False)


__all__ = ["trade_page_state_to_json"]
