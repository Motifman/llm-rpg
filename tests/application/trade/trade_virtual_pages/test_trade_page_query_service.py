"""TradePageQueryService: market / search / my_trades のスナップショット組み立て。"""

from __future__ import annotations

import json

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
from ai_rpg_world.application.trade.trade_virtual_pages.trade_page_query_service import (
    TradePageQueryService,
)
from ai_rpg_world.application.trade.trade_virtual_pages.trade_page_session_service import (
    TradePageSessionService,
)
from ai_rpg_world.infrastructure.repository.in_memory_global_market_listing_read_model_repository import (
    InMemoryGlobalMarketListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_personal_trade_listing_read_model_repository import (
    InMemoryPersonalTradeListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
)


class TestTradePageQueryService:
    def setup_method(self) -> None:
        self.global_repo = InMemoryGlobalMarketListingReadModelRepository()
        self.trade_repo = InMemoryTradeReadModelRepository()
        self.personal_repo = InMemoryPersonalTradeListingReadModelRepository()
        self.global_svc = GlobalMarketQueryService(self.global_repo)
        self.trade_svc = TradeQueryService(self.trade_repo)
        self.personal_svc = PersonalTradeQueryService(self.personal_repo)
        self.session = TradePageSessionService()
        self.query = TradePageQueryService(
            global_market_query_service=self.global_svc,
            personal_trade_query_service=self.personal_svc,
            trade_query_service=self.trade_svc,
            trade_page_session=self.session,
        )

    def test_market_snapshot_includes_rows_and_trade_refs(self) -> None:
        pid = 1
        self.session.on_enter_trade(pid)
        self.session.set_page_kind(pid, TradeVirtualPageKind.MARKET)
        raw = self.query.build_current_page_snapshot_json(pid)
        data = json.loads(raw)
        assert data["page_kind"] == "market"
        assert "rows" in data
        assert len(data["rows"]) >= 1
        row0 = data["rows"][0]
        assert "trade_ref" in row0
        assert "item_name" in row0
        tid = self.session.resolve_trade_ref(pid, row0["trade_ref"])
        assert tid is not None

    def test_search_snapshot_applies_item_name_price_and_rarity_filters(self) -> None:
        pid = 1
        self.session.on_enter_trade(pid)
        self.session.set_page_kind(pid, TradeVirtualPageKind.SEARCH)
        self.session.set_search_filters(
            pid,
            item_name="剣",
            min_price=400,
            max_price=600,
            rarities=["common"],
        )
        raw = self.query.build_current_page_snapshot_json(pid)
        data = json.loads(raw)
        assert data["page_kind"] == "search"
        for row in data["rows"]:
            assert "剣" in row["item_name"]
            assert 400 <= row["requested_gold"] <= 600
            assert row["item_rarity"] == "common"

    def test_my_trades_selling_only_lists_player_as_seller(self) -> None:
        pid = 1
        self.session.on_enter_trade(pid)
        self.session.set_page_kind(pid, TradeVirtualPageKind.MY_TRADES)
        self.session.set_my_trades_tab(pid, MyTradesTab.SELLING)
        raw = self.query.build_current_page_snapshot_json(pid)
        data = json.loads(raw)
        assert data["page_kind"] == "my_trades"
        assert data["active_tab"] == "selling"
        for row in data["rows"]:
            ref = row["trade_ref"]
            tid = self.session.resolve_trade_ref(pid, ref)
            assert tid is not None
            dto = self.trade_svc.get_trade_details(tid)
            assert dto.seller_id == pid

    def test_my_trades_incoming_lists_personal_trades_for_recipient(self) -> None:
        pid = 1
        self.session.on_enter_trade(pid)
        self.session.set_page_kind(pid, TradeVirtualPageKind.MY_TRADES)
        self.session.set_my_trades_tab(pid, MyTradesTab.INCOMING)
        raw = self.query.build_current_page_snapshot_json(pid)
        data = json.loads(raw)
        assert data["active_tab"] == "incoming"
        assert len(data["rows"]) >= 1
        row0 = data["rows"][0]
        assert "seller_name" in row0
        assert "item_name" in row0
        tid = self.session.resolve_trade_ref(pid, row0["trade_ref"])
        assert tid is not None
