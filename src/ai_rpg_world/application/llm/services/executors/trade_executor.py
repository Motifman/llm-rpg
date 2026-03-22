"""
Trade ツール（offer, accept, cancel）の実行。

ToolCommandMapper のサブマッパーとして、取引関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    invalid_arg_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_DECLINE,
    TOOL_NAME_TRADE_ENTER,
    TOOL_NAME_TRADE_EXIT,
    TOOL_NAME_TRADE_OFFER,
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
    ) -> None:
        self._trade_service = trade_service
        self._sns_mode_session = sns_mode_session

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。trade_service が None の場合は入退場のみ。"""
        handlers: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]] = {
            TOOL_NAME_TRADE_ENTER: self._execute_trade_enter,
            TOOL_NAME_TRADE_EXIT: self._execute_trade_exit,
        }
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
        return LlmCommandResultDto(success=True, message="取引所を開きました。")

    def _execute_trade_exit(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_mode_session is None:
            return unknown_tool("取引所モード状態が利用できません。")
        self._sns_mode_session.exit_trade_mode(player_id)
        return LlmCommandResultDto(success=True, message="取引所を閉じました。")

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
        if args.get("trade_id") is None:
            return invalid_arg_result("trade_id")
        try:
            result = self._trade_service.accept_trade(
                AcceptTradeCommand(trade_id=int(args["trade_id"]), buyer_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_trade_cancel(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_service is None:
            return unknown_tool("取引キャンセルツールはまだ利用できません。")
        if args.get("trade_id") is None:
            return invalid_arg_result("trade_id")
        try:
            result = self._trade_service.cancel_trade(
                CancelTradeCommand(trade_id=int(args["trade_id"]), player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_trade_decline(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._trade_service is None:
            return unknown_tool("取引拒否ツールはまだ利用できません。")
        if args.get("trade_id") is None:
            return invalid_arg_result("trade_id")
        try:
            result = self._trade_service.decline_trade(
                DeclineTradeCommand(trade_id=int(args["trade_id"]), decliner_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)
