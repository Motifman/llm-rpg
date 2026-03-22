"""取引所仮想ページの page session（非永続・player_id ごと）。"""

from __future__ import annotations

from typing import Dict, List, Optional

from ai_rpg_world.application.trade.trade_virtual_pages.kinds import (
    MyTradesTab,
    TradeVirtualPageKind,
)
from ai_rpg_world.application.trade.trade_virtual_pages.trade_page_session_state import (
    TradePageSessionState,
    clamp_trade_page_limit,
)


class TradePageSessionService:
    """現在画面・ref マップ・スナップショット世代を保持する。ドメインには ref を持ち込まない。"""

    def __init__(self) -> None:
        self._state_by_player: Dict[int, TradePageSessionState] = {}

    def get_state(self, player_id: int) -> TradePageSessionState:
        """状態が無い場合は market 既定で作成する（読み取り専用用途向け）。"""
        if player_id not in self._state_by_player:
            self._state_by_player[player_id] = TradePageSessionState.default_market()
        return self._state_by_player[player_id]

    def on_enter_trade(self, player_id: int) -> None:
        """trade_enter 成功時: market に戻し ref・世代を初期化。"""
        self._state_by_player[player_id] = TradePageSessionState.default_market()

    def on_exit_trade(self, player_id: int) -> None:
        """trade_exit 時: ページ状態を破棄。"""
        self._state_by_player.pop(player_id, None)

    def set_page_kind(self, player_id: int, kind: TradeVirtualPageKind) -> None:
        st = self.get_state(player_id)
        st.page_kind = kind

    def set_my_trades_tab(self, player_id: int, tab: MyTradesTab) -> None:
        st = self.get_state(player_id)
        st.my_trades_tab = tab

    def set_paging(self, player_id: int, *, limit: Optional[int] = None, offset: Optional[int] = None) -> None:
        st = self.get_state(player_id)
        if limit is not None:
            st.limit = clamp_trade_page_limit(limit)
        if offset is not None:
            st.offset = max(0, int(offset))

    def set_search_filters(
        self,
        player_id: int,
        *,
        item_name: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        item_types: Optional[List[str]] = None,
        rarities: Optional[List[str]] = None,
        equipment_types: Optional[List[str]] = None,
    ) -> None:
        st = self.get_state(player_id)
        if item_name is not None:
            st.item_name = item_name
        if min_price is not None:
            st.min_price = min_price
        if max_price is not None:
            st.max_price = max_price
        if item_types is not None:
            st.item_types = list(item_types)
        if rarities is not None:
            st.rarities = list(rarities)
        if equipment_types is not None:
            st.equipment_types = list(equipment_types)

    def bump_snapshot_generation(self, player_id: int) -> int:
        """同一条件の再取得などで ref を無効化する。世代を上げて ref マップを空にする。"""
        st = self.get_state(player_id)
        st.snapshot_generation += 1
        st.clear_ref_maps()
        return st.snapshot_generation

    def _next_ref(self, st: TradePageSessionState) -> str:
        st.ref_seq += 1
        return f"r_trade_{st.ref_seq:02d}"

    def issue_trade_ref(self, player_id: int, trade_id: int) -> str:
        st = self.get_state(player_id)
        ref = self._next_ref(st)
        st.ref_to_trade_id[ref] = trade_id
        return ref

    def resolve_trade_ref(self, player_id: int, ref: str) -> Optional[int]:
        return self.get_state(player_id).ref_to_trade_id.get(ref)


__all__ = ["TradePageSessionService"]
