"""取引所仮想ページのスナップショットを既存 Trade query に束ねて組み立てる。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from ai_rpg_world.application.trade.contracts.dtos import TradeDto
from ai_rpg_world.application.trade.contracts.global_market_dtos import (
    GlobalMarketFilterDto,
    GlobalMarketListingDto,
)
from ai_rpg_world.application.trade.contracts.personal_trade_dtos import PersonalTradeListingDto
from ai_rpg_world.application.trade.services.global_market_query_service import (
    GlobalMarketQueryService,
)
from ai_rpg_world.application.trade.services.personal_trade_query_service import (
    PersonalTradeQueryService,
)
from ai_rpg_world.application.trade.services.trade_query_service import TradeQueryService
from ai_rpg_world.application.trade.trade_virtual_pages.kinds import (
    MyTradesTab,
    TradeVirtualPageKind,
)
from ai_rpg_world.application.trade.trade_virtual_pages.snapshot_json import (
    trade_page_full_snapshot_json,
)
from ai_rpg_world.application.trade.trade_virtual_pages.trade_page_session_service import (
    TradePageSessionService,
)
from ai_rpg_world.application.trade.trade_virtual_pages.trade_page_session_state import (
    TradePageSessionState,
)


def _cursor_stream_slice(
    fetch: Callable[[Optional[str], int], Tuple[List[Any], Optional[str]]],
    offset: int,
    limit: int,
) -> Tuple[List[Any], Optional[str]]:
    """カーソルページング API から offset/limit 相当のウィンドウを取り出す。"""
    if offset < 0 or limit <= 0:
        return [], None
    cursor: Optional[str] = None
    skip_remaining = offset
    out: List[Any] = []
    last_next: Optional[str] = None

    while len(out) < limit:
        need = skip_remaining + (limit - len(out))
        batch_limit = min(100, max(need, 1))
        items, next_c = fetch(cursor, batch_limit)
        last_next = next_c
        if not items:
            return out, None

        if skip_remaining > 0:
            if len(items) <= skip_remaining:
                skip_remaining -= len(items)
                cursor = next_c
                if cursor is None:
                    return [], None
                continue
            items = items[skip_remaining:]
            skip_remaining = 0

        for it in items:
            if len(out) >= limit:
                break
            out.append(it)

        if len(out) >= limit:
            return out, last_next

        cursor = next_c
        if cursor is None:
            break

    return out, last_next if len(out) == limit else None


def _state_to_global_filter(st: TradePageSessionState) -> Optional[GlobalMarketFilterDto]:
    def _nz_list(xs: List[str]) -> Optional[List[str]]:
        return xs if xs else None

    name = st.item_name.strip() if st.item_name else None
    return GlobalMarketFilterDto(
        item_name=name or None,
        item_types=_nz_list(st.item_types),
        rarities=_nz_list(st.rarities),
        equipment_types=_nz_list(st.equipment_types),
        min_price=st.min_price,
        max_price=st.max_price,
    )


class TradePageQueryService:
    """TradePageSession の状態に従い、market / search / my_trades のスナップショット JSON を組み立てる。"""

    def __init__(
        self,
        *,
        global_market_query_service: GlobalMarketQueryService,
        personal_trade_query_service: PersonalTradeQueryService,
        trade_query_service: TradeQueryService,
        trade_page_session: TradePageSessionService,
    ) -> None:
        self._global_market = global_market_query_service
        self._personal_trade = personal_trade_query_service
        self._trade_query = trade_query_service
        self._session = trade_page_session

    def build_current_page_snapshot_json(self, player_id: int) -> str:
        """現在ページのスナップショット JSON。呼び出しごとに世代を上げ、trade_ref を再発行する。"""
        self._session.bump_snapshot_generation(player_id)
        st = self._session.get_state(player_id)
        kind = st.page_kind
        if kind == TradeVirtualPageKind.MARKET:
            rows, next_c = self._build_market_or_search_rows(player_id, st, filter_for_search=False)
        elif kind == TradeVirtualPageKind.SEARCH:
            rows, next_c = self._build_market_or_search_rows(player_id, st, filter_for_search=True)
        elif kind == TradeVirtualPageKind.MY_TRADES:
            rows, next_c = self._build_my_trades_rows(player_id, st)
        else:
            rows, next_c = [], None

        st_after = self._session.get_state(player_id)
        return trade_page_full_snapshot_json(st_after, rows, next_c)

    def _build_market_or_search_rows(
        self,
        player_id: int,
        st: TradePageSessionState,
        *,
        filter_for_search: bool,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        filt: Optional[GlobalMarketFilterDto] = (
            _state_to_global_filter(st) if filter_for_search else None
        )

        def fetch(cursor: Optional[str], batch_limit: int) -> Tuple[List[GlobalMarketListingDto], Optional[str]]:
            r = self._global_market.get_market_listings(
                filter_dto=filt,
                limit=batch_limit,
                cursor=cursor,
            )
            return r.listings, r.next_cursor

        listings, next_c = _cursor_stream_slice(fetch, st.offset, st.limit)
        rows: List[Dict[str, Any]] = []
        for listing in listings:
            ref = self._session.issue_trade_ref(player_id, listing.trade_id)
            rows.append(self._market_row(ref, listing))
        return rows, next_c

    def _market_row(self, trade_ref: str, listing: GlobalMarketListingDto) -> Dict[str, Any]:
        return {
            "trade_ref": trade_ref,
            "item_name": listing.item_name,
            "requested_gold": listing.requested_gold,
            "item_type": listing.item_type,
            "item_rarity": listing.item_rarity,
            "item_equipment_type": listing.item_equipment_type,
            "created_at": listing.created_at,
            "status": listing.status,
        }

    def _build_my_trades_rows(
        self,
        player_id: int,
        st: TradePageSessionState,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if st.my_trades_tab == MyTradesTab.SELLING:
            return self._build_selling_rows(player_id, st)
        return self._build_incoming_rows(player_id, st)

    def _build_selling_rows(
        self,
        player_id: int,
        st: TradePageSessionState,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """出品一覧: ACTIVE のみを `get_active_trades_as_seller` の専用ストリームでページングする。"""

        def fetch(cur: Optional[str], batch_limit: int) -> Tuple[List[TradeDto], Optional[str]]:
            r = self._trade_query.get_active_trades_as_seller(
                player_id, limit=batch_limit, cursor=cur
            )
            return r.trades, r.next_cursor

        trades, next_c = _cursor_stream_slice(fetch, st.offset, st.limit)
        rows: List[Dict[str, Any]] = []
        for t in trades:
            ref = self._session.issue_trade_ref(player_id, t.trade_id)
            rows.append(self._selling_row(ref, t))
        return rows, next_c

    def _selling_row(self, trade_ref: str, t: TradeDto) -> Dict[str, Any]:
        return {
            "trade_ref": trade_ref,
            "item_name": t.item_name,
            "requested_gold": t.requested_gold,
            "status": t.status,
        }

    def _build_incoming_rows(
        self,
        player_id: int,
        st: TradePageSessionState,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        def fetch(cur: Optional[str], batch_limit: int) -> Tuple[List[PersonalTradeListingDto], Optional[str]]:
            lim = min(50, batch_limit)
            r = self._personal_trade.get_personal_trades(player_id, limit=lim, cursor=cur)
            return r.listings, r.next_cursor

        listings, next_c = _cursor_stream_slice(fetch, st.offset, st.limit)
        rows: List[Dict[str, Any]] = []
        for listing in listings:
            ref = self._session.issue_trade_ref(player_id, listing.trade_id)
            rows.append(self._incoming_row(ref, listing))
        return rows, next_c

    def _incoming_row(self, trade_ref: str, listing: PersonalTradeListingDto) -> Dict[str, Any]:
        return {
            "trade_ref": trade_ref,
            "seller_name": listing.seller_name,
            "item_name": listing.item_name,
            "requested_gold": listing.requested_gold,
        }


__all__ = ["TradePageQueryService"]
