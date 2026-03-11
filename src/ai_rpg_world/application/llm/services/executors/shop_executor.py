"""
Shop ツール（purchase, list_item, unlist_item）の実行。

ToolCommandMapper のサブマッパーとして、ショップ関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SHOP_LIST_ITEM,
    TOOL_NAME_SHOP_PURCHASE,
    TOOL_NAME_SHOP_UNLIST_ITEM,
)
from ai_rpg_world.application.shop.contracts.commands import (
    ListShopItemCommand,
    PurchaseFromShopCommand,
    UnlistShopItemCommand,
)


class ShopToolExecutor:
    """
    Shop ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返し、
    ToolCommandMapper が _executor_map にマージする。
    """

    def __init__(self, shop_service: Optional[Any] = None) -> None:
        self._shop_service = shop_service

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。shop_service が None の場合は空辞書。"""
        if self._shop_service is None:
            return {}
        return {
            TOOL_NAME_SHOP_PURCHASE: self._execute_shop_purchase,
            TOOL_NAME_SHOP_LIST_ITEM: self._execute_shop_list_item,
            TOOL_NAME_SHOP_UNLIST_ITEM: self._execute_shop_unlist_item,
        }

    def _execute_shop_purchase(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._shop_service is None:
            return unknown_tool("ショップ購入ツールはまだ利用できません。")
        try:
            result = self._shop_service.purchase_from_shop(
                PurchaseFromShopCommand(
                    shop_id=int(args["shop_id"]),
                    listing_id=int(args["listing_id"]),
                    buyer_id=player_id,
                    quantity=int(args.get("quantity", 1)),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_shop_list_item(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._shop_service is None:
            return unknown_tool("ショップ出品ツールはまだ利用できません。")
        try:
            result = self._shop_service.list_shop_item(
                ListShopItemCommand(
                    shop_id=int(args["shop_id"]),
                    player_id=player_id,
                    slot_id=int(args["slot_id"]),
                    price_per_unit=int(args["price_per_unit"]),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_shop_unlist_item(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._shop_service is None:
            return unknown_tool("ショップ取り下げツールはまだ利用できません。")
        try:
            result = self._shop_service.unlist_shop_item(
                UnlistShopItemCommand(
                    shop_id=int(args["shop_id"]),
                    listing_id=int(args["listing_id"]),
                    player_id=player_id,
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)
