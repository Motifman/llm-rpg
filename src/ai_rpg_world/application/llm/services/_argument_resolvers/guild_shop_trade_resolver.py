"""ギルド・ショップ・取引系ツールの引数解決。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    GuildToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ShopListingToolRuntimeTargetDto,
    ShopToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    require_target_type,
    safe_int,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_GUILD_ADD_MEMBER,
    TOOL_NAME_GUILD_CHANGE_ROLE,
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_GUILD_LEAVE,
    TOOL_NAME_GUILD_WITHDRAW_BANK,
    TOOL_NAME_SHOP_LIST_ITEM,
    TOOL_NAME_SHOP_PURCHASE,
    TOOL_NAME_SHOP_UNLIST_ITEM,
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_DECLINE,
    TOOL_NAME_TRADE_OFFER,
)


class GuildShopTradeArgumentResolver:
    """ギルド・ショップ・取引系ツールの引数解決。"""

    def resolve_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Optional[Dict[str, Any]]:
        if tool_name == TOOL_NAME_GUILD_CREATE:
            return self._resolve_guild_create(args, runtime_context)
        if tool_name == TOOL_NAME_GUILD_ADD_MEMBER:
            return self._resolve_guild_add_member(args, runtime_context)
        if tool_name == TOOL_NAME_GUILD_CHANGE_ROLE:
            return self._resolve_guild_change_role(args, runtime_context)
        if tool_name == TOOL_NAME_GUILD_DISBAND:
            return self._resolve_guild_label(args, runtime_context)
        if tool_name == TOOL_NAME_GUILD_LEAVE:
            return self._resolve_guild_label(args, runtime_context)
        if tool_name == TOOL_NAME_GUILD_DEPOSIT_BANK:
            return self._resolve_guild_label(args, runtime_context, include_amount=True)
        if tool_name == TOOL_NAME_GUILD_WITHDRAW_BANK:
            return self._resolve_guild_label(args, runtime_context, include_amount=True)
        if tool_name == TOOL_NAME_SHOP_PURCHASE:
            return self._resolve_shop_purchase(args, runtime_context)
        if tool_name == TOOL_NAME_SHOP_LIST_ITEM:
            return self._resolve_shop_list_item(args, runtime_context)
        if tool_name == TOOL_NAME_SHOP_UNLIST_ITEM:
            return self._resolve_shop_unlist_item(args, runtime_context)
        if tool_name == TOOL_NAME_TRADE_OFFER:
            return self._resolve_trade_offer(args, runtime_context)
        if tool_name == TOOL_NAME_TRADE_ACCEPT:
            return self._resolve_trade_ref_mutation(args)
        if tool_name == TOOL_NAME_TRADE_CANCEL:
            return self._resolve_trade_ref_mutation(args)
        if tool_name == TOOL_NAME_TRADE_DECLINE:
            return self._resolve_trade_ref_mutation(args)
        return None

    def _resolve_guild_create(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        spot_id = runtime_context.current_spot_id
        area_ids = runtime_context.current_area_ids
        if spot_id is None:
            raise ToolArgumentResolutionException(
                "現在地スポットが取得できていません。",
                "MISSING_CURRENT_SPOT",
            )
        if not area_ids:
            raise ToolArgumentResolutionException(
                "現在地がロケーションエリアに含まれていません。ギルドはロケーション内で作成してください。",
                "MISSING_CURRENT_AREA",
            )
        name = args.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ToolArgumentResolutionException(
                "ギルド名が指定されていません。",
                "MISSING_GUILD_NAME",
            )
        location_area_id = area_ids[0]
        return {
            "spot_id": spot_id,
            "location_area_id": location_area_id,
            "name": name.strip(),
            "description": (args.get("description") or "").strip(),
        }

    def _resolve_guild_add_member(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        base = self._resolve_guild_label(args, runtime_context)
        label = args.get("target_player_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "招待するプレイヤーラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target_type(
            label,
            runtime_context,
            "プレイヤーラベル",
            (PlayerToolRuntimeTargetDto,),
        )
        if target.player_id is None:
            raise ToolArgumentResolutionException(
                f"プレイヤーとして解決できません: {label}",
                "INVALID_TARGET_KIND",
            )
        base["new_member_player_id"] = target.player_id
        return base

    def _resolve_guild_change_role(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        base = self._resolve_guild_label(args, runtime_context)
        label = args.get("target_member_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "役職変更するメンバーラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target_type(
            label,
            runtime_context,
            "メンバーラベル",
            (PlayerToolRuntimeTargetDto,),
        )
        if target.player_id is None:
            raise ToolArgumentResolutionException(
                f"メンバーとして解決できません: {label}",
                "INVALID_TARGET_KIND",
            )
        new_role = args.get("new_role")
        if new_role not in ("leader", "officer", "member"):
            raise ToolArgumentResolutionException(
                f"無効な役職です: {new_role}。leader / officer / member のいずれかを指定してください。",
                "INVALID_ROLE",
            )
        base["target_player_id"] = target.player_id
        base["new_role"] = new_role
        return base

    def _resolve_guild_label(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
        include_amount: bool = False,
    ) -> Dict[str, Any]:
        label = args.get("guild_label")
        target = require_target_type(
            label,
            runtime_context,
            "ギルドラベル",
            (GuildToolRuntimeTargetDto,),
        )
        if target.guild_id is None:
            raise ToolArgumentResolutionException(
                f"ギルドとして解決できません: {label}",
                "INVALID_TARGET_KIND",
            )
        result: Dict[str, Any] = {"guild_id": target.guild_id}
        if include_amount:
            amount = args.get("amount")
            if amount is not None:
                result["amount"] = safe_int(amount, "amount", min_val=0)
        return result

    def _resolve_shop_purchase(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        shop_label = args.get("shop_label")
        listing_label = args.get("listing_label")
        listing_id_raw = args.get("listing_id")
        if listing_label is not None:
            listing_target = require_target_type(
                listing_label,
                runtime_context,
                "出品ラベル",
                (ShopListingToolRuntimeTargetDto,),
            )
            if listing_target.shop_id is None or listing_target.listing_id is None:
                raise ToolArgumentResolutionException(
                    f"出品として解決できません: {listing_label}",
                    "INVALID_TARGET_KIND",
                )
            shop_id = listing_target.shop_id
            listing_id = listing_target.listing_id
        elif listing_id_raw is not None:
            shop_target = require_target_type(
                shop_label,
                runtime_context,
                "ショップラベル",
                (ShopToolRuntimeTargetDto,),
            )
            if shop_target.shop_id is None:
                raise ToolArgumentResolutionException(
                    f"ショップとして解決できません: {shop_label}",
                    "INVALID_TARGET_KIND",
                )
            shop_id = shop_target.shop_id
            listing_id = safe_int(listing_id_raw, "listing_id", min_val=1)
        else:
            raise ToolArgumentResolutionException(
                "listing_label または listing_id を指定してください。",
                "INVALID_TARGET_LABEL",
            )
        quantity_raw = args.get("quantity", 1)
        quantity = safe_int(quantity_raw, "quantity", min_val=1)
        return {
            "shop_id": shop_id,
            "listing_id": listing_id,
            "quantity": quantity,
        }

    def _resolve_shop_list_item(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        shop_label = args.get("shop_label")
        shop_target = require_target_type(
            shop_label,
            runtime_context,
            "ショップラベル",
            (ShopToolRuntimeTargetDto,),
        )
        if shop_target.shop_id is None:
            raise ToolArgumentResolutionException(
                f"ショップとして解決できません: {shop_label}",
                "INVALID_TARGET_KIND",
            )
        item_label = args.get("inventory_item_label")
        item_target = require_target_type(
            item_label,
            runtime_context,
            "在庫アイテムラベル",
            (InventoryToolRuntimeTargetDto,),
        )
        if item_target.inventory_slot_id is None:
            raise ToolArgumentResolutionException(
                f"在庫アイテムとして解決できません: {item_label}",
                "INVALID_TARGET_KIND",
            )
        price = args.get("price_per_unit")
        if price is None:
            raise ToolArgumentResolutionException(
                "price_per_unit が指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        price_int = safe_int(price, "price_per_unit", min_val=0)
        return {
            "shop_id": shop_target.shop_id,
            "slot_id": item_target.inventory_slot_id,
            "price_per_unit": price_int,
        }

    def _resolve_shop_unlist_item(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        shop_label = args.get("shop_label")
        listing_label = args.get("listing_label")
        listing_id_raw = args.get("listing_id")
        if listing_label is not None:
            listing_target = require_target_type(
                listing_label,
                runtime_context,
                "出品ラベル",
                (ShopListingToolRuntimeTargetDto,),
            )
            if listing_target.shop_id is None or listing_target.listing_id is None:
                raise ToolArgumentResolutionException(
                    f"出品として解決できません: {listing_label}",
                    "INVALID_TARGET_KIND",
                )
            return {
                "shop_id": listing_target.shop_id,
                "listing_id": listing_target.listing_id,
            }
        elif listing_id_raw is not None:
            shop_target = require_target_type(
                shop_label,
                runtime_context,
                "ショップラベル",
                (ShopToolRuntimeTargetDto,),
            )
            if shop_target.shop_id is None:
                raise ToolArgumentResolutionException(
                    f"ショップとして解決できません: {shop_label}",
                    "INVALID_TARGET_KIND",
                )
            listing_id = safe_int(listing_id_raw, "listing_id", min_val=1)
            return {"shop_id": shop_target.shop_id, "listing_id": listing_id}
        else:
            raise ToolArgumentResolutionException(
                "listing_label または listing_id を指定してください。",
                "INVALID_TARGET_LABEL",
            )

    def _resolve_trade_offer(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        item_label = args.get("inventory_item_label")
        item_target = require_target_type(
            item_label,
            runtime_context,
            "在庫アイテムラベル",
            (InventoryToolRuntimeTargetDto,),
        )
        if (
            item_target.inventory_slot_id is None
            or item_target.item_instance_id is None
        ):
            raise ToolArgumentResolutionException(
                f"出品に使えない在庫ラベルです: {item_label}",
                "INVALID_TARGET_KIND",
            )
        requested_gold = args.get("requested_gold")
        if requested_gold is None:
            raise ToolArgumentResolutionException(
                "requested_gold が指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        requested_gold_int = safe_int(requested_gold, "requested_gold", min_val=0)
        slot_id = item_target.inventory_slot_id
        if slot_id is None:
            raise ToolArgumentResolutionException(
                f"出品に使えない在庫ラベルです: {item_label}",
                "INVALID_TARGET_KIND",
            )
        result: Dict[str, Any] = {
            "item_instance_id": item_target.item_instance_id,
            "slot_id": slot_id,
            "requested_gold": requested_gold_int,
        }
        target_player_label = args.get("target_player_label")
        target_player_id = args.get("target_player_id")
        if target_player_label is not None:
            player_target = require_target_type(
                target_player_label,
                runtime_context,
                "プレイヤーラベル",
                (PlayerToolRuntimeTargetDto,),
            )
            if player_target.player_id is not None:
                result["target_player_id"] = player_target.player_id
        elif target_player_id is not None:
            result["target_player_id"] = safe_int(
                target_player_id, "target_player_id", min_val=1
            )
        return result

    def _resolve_trade_ref_mutation(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """取引ミューテーションは page-local `trade_ref` のみ受理する。"""
        ref = args.get("trade_ref")
        if ref is not None and str(ref).strip():
            return {"trade_ref": str(ref).strip()}
        raise ToolArgumentResolutionException(
            "trade_ref が指定されていません。trade_view_current_page のスナップショットに含まれる r_trade_* を指定してください。",
            "INVALID_TARGET_LABEL",
        )
