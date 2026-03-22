"""TradePageSessionService: 画面遷移・ref・世代更新。"""

from ai_rpg_world.application.trade.trade_virtual_pages import (
    MyTradesTab,
    TradeVirtualPageKind,
)
from ai_rpg_world.application.trade.trade_virtual_pages.trade_page_session_service import (
    TradePageSessionService,
)


class TestTradePageSessionService:
    def test_market_search_my_trades_navigation(self) -> None:
        svc = TradePageSessionService()
        pid = 1
        svc.on_enter_trade(pid)
        assert svc.get_state(pid).page_kind == TradeVirtualPageKind.MARKET

        svc.set_page_kind(pid, TradeVirtualPageKind.SEARCH)
        svc.set_search_filters(pid, item_name="sword", min_price=10, max_price=100)
        assert svc.get_state(pid).page_kind == TradeVirtualPageKind.SEARCH
        assert svc.get_state(pid).item_name == "sword"

        svc.set_page_kind(pid, TradeVirtualPageKind.MY_TRADES)
        svc.set_my_trades_tab(pid, MyTradesTab.INCOMING)
        assert svc.get_state(pid).page_kind == TradeVirtualPageKind.MY_TRADES
        assert svc.get_state(pid).my_trades_tab == MyTradesTab.INCOMING

    def test_bump_snapshot_generation_clears_trade_refs(self) -> None:
        svc = TradePageSessionService()
        pid = 2
        svc.on_enter_trade(pid)
        ref = svc.issue_trade_ref(pid, 99)
        assert svc.resolve_trade_ref(pid, ref) == 99
        svc.bump_snapshot_generation(pid)
        assert svc.resolve_trade_ref(pid, ref) is None
        assert svc.get_state(pid).snapshot_generation == 1

    def test_on_exit_trade_removes_state(self) -> None:
        svc = TradePageSessionService()
        pid = 3
        svc.on_enter_trade(pid)
        svc.set_page_kind(pid, TradeVirtualPageKind.SEARCH)
        svc.on_exit_trade(pid)
        svc.on_enter_trade(pid)
        assert svc.get_state(pid).page_kind == TradeVirtualPageKind.MARKET
