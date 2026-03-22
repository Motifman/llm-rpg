"""取引所仮想ページの page session 状態（メモリ上・プレイヤー単位）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ai_rpg_world.application.trade.trade_virtual_pages.kinds import (
    MyTradesTab,
    TradeVirtualPageKind,
)

_DEFAULT_PAGE_LIMIT = 20
_MAX_PAGE_LIMIT = 100


def clamp_trade_page_limit(limit: Optional[int]) -> int:
    """limit 省略時は 20、最大 100 に収める。"""
    if limit is None:
        return _DEFAULT_PAGE_LIMIT
    return max(1, min(int(limit), _MAX_PAGE_LIMIT))


@dataclass
class TradePageSessionState:
    """現在画面・タブ・ページング・検索条件・ref マップ・スナップショット世代を保持する。"""

    page_kind: TradeVirtualPageKind = TradeVirtualPageKind.MARKET
    my_trades_tab: MyTradesTab = MyTradesTab.SELLING
    limit: int = _DEFAULT_PAGE_LIMIT
    offset: int = 0
    item_name: str = ""
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    item_types: List[str] = field(default_factory=list)
    rarities: List[str] = field(default_factory=list)
    equipment_types: List[str] = field(default_factory=list)
    snapshot_generation: int = 0
    ref_seq: int = 0
    ref_to_trade_id: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def default_market(cls) -> TradePageSessionState:
        """取引所入室直後: market。"""
        return cls(
            page_kind=TradeVirtualPageKind.MARKET,
            my_trades_tab=MyTradesTab.SELLING,
            limit=_DEFAULT_PAGE_LIMIT,
            offset=0,
        )

    def clear_ref_maps(self) -> None:
        """同一世代内の ref を破棄（世代更新時に呼ぶ）。"""
        self.ref_to_trade_id.clear()


__all__ = [
    "TradePageSessionState",
    "clamp_trade_page_limit",
]
