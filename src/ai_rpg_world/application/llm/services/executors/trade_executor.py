"""
Trade ツール（offer, accept, cancel）の実行。

ToolCommandMapper のサブマッパーとして、取引関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    invalid_arg_result,
    invalid_arg_value_result,
    unknown_tool,
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
from ai_rpg_world.application.social.services.active_game_app_session_service import (
    ActiveGameAppConflictError,
)
from ai_rpg_world.application.trade.contracts.commands import (
    AcceptTradeCommand,
    CancelTradeCommand,
    DeclineTradeCommand,
    OfferItemCommand,
)
from ai_rpg_world.application.trade.trade_virtual_pages.kinds import (
    MyTradesTab,
    TradeVirtualPageKind,
)


def _parse_trade_virtual_page_kind(raw: Any) -> Optional[TradeVirtualPageKind]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    for k in TradeVirtualPageKind:
        if k.value == s:
            return k
    return None


def _parse_my_trades_tab_strict(raw: Any) -> Optional[MyTradesTab]:
    """incoming|selling のみ受理。空・未知値は None。"""
    if raw is None:
        return None
    t = str(raw).strip().lower()
    if not t:
        return None
    if t == MyTradesTab.INCOMING.value:
        return MyTradesTab.INCOMING
    if t == MyTradesTab.SELLING.value:
        return MyTradesTab.SELLING
    return None


def _non_empty_str_list(raw: Any) -> Optional[List[str]]:
    if raw is None:
        return None
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip()]
        return out or None
    return None


def _optional_int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class TradeToolExecutor:
    """
    Trade ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返し、
    ToolCommandMapper が _executor_map にマージする。
    """

    def __init__(
        self,
        trade_service: Optional[Any] = None,
        sns_mode_session: Optional[Any] = None,
        trade_page_session: Optional[Any] = None,
        trade_page_query_service: Optional[Any] = None,
    ) -> None:
        self._trade_service = trade_service
        self._sns_mode_session = sns_mode_session
        self._trade_page_session = trade_page_session
        self._trade_page_query_service = trade_page_query_service

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。trade_service が None の場合は入退場のみ。"""
        handlers: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]] = {
            TOOL_NAME_TRADE_ENTER: self._execute_trade_enter,
            TOOL_NAME_TRADE_EXIT: self._execute_trade_exit,
        }
        if (
            self._trade_page_query_service is not None
            and self._trade_page_session is not None
        ):
            handlers[TOOL_NAME_TRADE_VIEW_CURRENT_PAGE] = self._execute_view_current_page
            handlers[TOOL_NAME_TRADE_PAGE_REFRESH] = self._execute_page_refresh
            handlers[TOOL_NAME_TRADE_OPEN_PAGE] = self._execute_open_page
            handlers[TOOL_NAME_TRADE_PAGE_NEXT] = self._execute_page_next
            handlers[TOOL_NAME_TRADE_SWITCH_TAB] = self._execute_switch_tab
        if self._trade_service is None:
            return handlers
        handlers.update(
            {
                TOOL_NAME_TRADE_OFFER: self._execute_trade_offer,
                TOOL_NAME_TRADE_ACCEPT: self._execute_trade_accept,
                TOOL_NAME_TRADE_CANCEL: self._execute_trade_cancel,
                TOOL_NAME_TRADE_DECLINE: self._execute_trade_decline,
            }
        )
        return handlers

    def _execute_trade_enter(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_mode_session is None:
            return unknown_tool("取引所モード状態が利用できません。")
        try:
            self._sns_mode_session.enter_trade_mode(player_id)
        except ActiveGameAppConflictError as e:
            return LlmCommandResultDto(success=False, message=str(e))
        if self._trade_page_session is not None:
            self._trade_page_session.on_enter_trade(player_id)
        return LlmCommandResultDto(success=True, message="取引所を開きました。")

    def _execute_trade_exit(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_mode_session is None:
            return unknown_tool("取引所モード状態が利用できません。")
        self._sns_mode_session.exit_trade_mode(player_id)
        if self._trade_page_session is not None:
            self._trade_page_session.on_exit_trade(player_id)
        return LlmCommandResultDto(success=True, message="取引所を閉じました。")

    def _snapshot_message(self, player_id: int) -> str:
        assert self._trade_page_query_service is not None
        return self._trade_page_query_service.build_current_page_snapshot_json(player_id)

    def _execute_view_current_page(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_page_query_service is None:
            return unknown_tool("仮想取引所画面が利用できません。")
        try:
            text = self._snapshot_message(player_id)
            return LlmCommandResultDto(success=True, message=text)
        except Exception as e:
            return exception_result(e)

    def _execute_page_refresh(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        return self._execute_view_current_page(player_id, args)

    def _execute_open_page(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_page_session is None or self._trade_page_query_service is None:
            return unknown_tool("仮想取引所画面が利用できません。")
        kind = _parse_trade_virtual_page_kind(args.get("page"))
        if kind is None:
            return invalid_arg_result("page")
        sess = self._trade_page_session
        try:
            if kind == TradeVirtualPageKind.MARKET:
                sess.set_page_kind(player_id, TradeVirtualPageKind.MARKET)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="マーケット一覧へ遷移しました。")
            if kind == TradeVirtualPageKind.SEARCH:
                sess.set_page_kind(player_id, TradeVirtualPageKind.SEARCH)
                sess.clear_search_filters(player_id)
                iname = args.get("item_name")
                if iname is not None:
                    sess.set_search_filters(player_id, item_name=str(iname))
                mp = _optional_int(args.get("min_price"))
                if mp is not None:
                    sess.set_search_filters(player_id, min_price=mp)
                mxp = _optional_int(args.get("max_price"))
                if mxp is not None:
                    sess.set_search_filters(player_id, max_price=mxp)
                itypes = _non_empty_str_list(args.get("item_types"))
                if itypes is not None:
                    sess.set_search_filters(player_id, item_types=itypes)
                rar = _non_empty_str_list(args.get("rarities"))
                if rar is not None:
                    sess.set_search_filters(player_id, rarities=rar)
                eqt = _non_empty_str_list(args.get("equipment_types"))
                if eqt is not None:
                    sess.set_search_filters(player_id, equipment_types=eqt)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="検索画面へ遷移しました。")
            if kind == TradeVirtualPageKind.MY_TRADES:
                raw_tab = args.get("my_trades_tab")
                if raw_tab is None or (
                    isinstance(raw_tab, str) and not raw_tab.strip()
                ):
                    tab = MyTradesTab.SELLING
                else:
                    tab = _parse_my_trades_tab_strict(raw_tab)
                    if tab is None:
                        return invalid_arg_value_result(
                            "my_trades_tab", "incoming|selling"
                        )
                sess.set_page_kind(player_id, TradeVirtualPageKind.MY_TRADES)
                sess.set_my_trades_tab(player_id, tab)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="自分の取引一覧へ遷移しました。")
        except Exception as e:
            return exception_result(e)
        return LlmCommandResultDto(success=False, message="未対応の画面です。")

    def _execute_page_next(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_page_session is None:
            return unknown_tool("仮想取引所画面が利用できません。")
        try:
            st = self._trade_page_session.get_state(player_id)
            new_offset = st.offset + st.limit
            self._trade_page_session.set_paging(player_id, offset=new_offset)
            return LlmCommandResultDto(success=True, message="次ページへ進めました。")
        except Exception as e:
            return exception_result(e)

    def _execute_switch_tab(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_page_session is None:
            return unknown_tool("仮想取引所画面が利用できません。")
        raw_tab = args.get("tab")
        if raw_tab is None or not str(raw_tab).strip():
            return invalid_arg_result("tab")
        tab = _parse_my_trades_tab_strict(raw_tab)
        if tab is None:
            return invalid_arg_value_result("tab", "incoming|selling")
        st = self._trade_page_session.get_state(player_id)
        if st.page_kind != TradeVirtualPageKind.MY_TRADES:
            return LlmCommandResultDto(
                success=False,
                message="my_trades 画面でのみタブを切り替えられます。",
            )
        try:
            self._trade_page_session.set_my_trades_tab(player_id, tab)
            self._trade_page_session.set_paging(player_id, offset=0)
            return LlmCommandResultDto(success=True, message="タブを切り替えました。")
        except Exception as e:
            return exception_result(e)

    def _resolve_trade_id(self, player_id: int, args: Dict[str, Any]) -> Optional[int]:
        ref = args.get("trade_ref")
        if ref is not None and str(ref).strip() and self._trade_page_session is not None:
            resolved = self._trade_page_session.resolve_trade_ref(
                player_id, str(ref).strip()
            )
            if resolved is not None:
                return int(resolved)
        return None

    def _execute_trade_offer(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_service is None:
            return unknown_tool("取引出品ツールはまだ利用できません。")
        for key in ("item_instance_id", "slot_id", "requested_gold"):
            if args.get(key) is None:
                return invalid_arg_result(key)
        try:
            result = self._trade_service.offer_item(
                OfferItemCommand(
                    seller_id=player_id,
                    item_instance_id=int(args["item_instance_id"]),
                    slot_id=int(args["slot_id"]),
                    requested_gold=int(args["requested_gold"]),
                    is_direct=args.get("target_player_id") is not None,
                    target_player_id=args.get("target_player_id"),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_trade_accept(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_service is None:
            return unknown_tool("取引受諾ツールはまだ利用できません。")
        tid = self._resolve_trade_id(player_id, args)
        if tid is None:
            return invalid_arg_result("trade_ref")
        try:
            result = self._trade_service.accept_trade(
                AcceptTradeCommand(trade_id=tid, buyer_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_trade_cancel(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_service is None:
            return unknown_tool("取引キャンセルツールはまだ利用できません。")
        tid = self._resolve_trade_id(player_id, args)
        if tid is None:
            return invalid_arg_result("trade_ref")
        try:
            result = self._trade_service.cancel_trade(
                CancelTradeCommand(trade_id=tid, player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_trade_decline(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_service is None:
            return unknown_tool("取引拒否ツールはまだ利用できません。")
        tid = self._resolve_trade_id(player_id, args)
        if tid is None:
            return invalid_arg_result("trade_ref")
        try:
            result = self._trade_service.decline_trade(
                DeclineTradeCommand(trade_id=tid, decliner_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)
