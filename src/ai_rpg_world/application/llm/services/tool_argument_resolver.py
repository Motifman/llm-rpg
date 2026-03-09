"""LLM の UI 向けラベル引数を canonical args に解決する。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    AttentionLevelToolRuntimeTargetDto,
    ChestItemToolRuntimeTargetDto,
    ChestToolRuntimeTargetDto,
    ConversationChoiceToolRuntimeTargetDto,
    DestinationToolRuntimeTargetDto,
    GuildToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
    NpcToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    QuestToolRuntimeTargetDto,
    SkillToolRuntimeTargetDto,
    ShopListingToolRuntimeTargetDto,
    ShopToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
    TradeToolRuntimeTargetDto,
    WorldObjectToolRuntimeTargetDto,
    ResourceToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import IToolArgumentResolver
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_LEAVE,
    TOOL_NAME_GUILD_WITHDRAW_BANK,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_QUEST_ACCEPT,
    TOOL_NAME_QUEST_APPROVE,
    TOOL_NAME_QUEST_CANCEL,
    TOOL_NAME_SAY,
    TOOL_NAME_SHOP_LIST_ITEM,
    TOOL_NAME_SHOP_PURCHASE,
    TOOL_NAME_SHOP_UNLIST_ITEM,
    TOOL_NAME_TRADE_ACCEPT,
    TOOL_NAME_TRADE_CANCEL,
    TOOL_NAME_TRADE_OFFER,
    TOOL_NAME_WHISPER,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.world.value_object.facing import Facing


class ToolArgumentResolutionException(Exception):
    """UI ラベル引数を解決できないときの例外。"""

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


class DefaultToolArgumentResolver(IToolArgumentResolver):
    """ツール名ごとに UI ラベルを既存アプリケーション層の引数へ解決する。"""

    def resolve(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        if not isinstance(tool_name, str):
            raise TypeError("tool_name must be str")
        if arguments is not None and not isinstance(arguments, dict):
            raise TypeError("arguments must be dict or None")
        if not isinstance(runtime_context, ToolRuntimeContextDto):
            raise TypeError("runtime_context must be ToolRuntimeContextDto")

        args = arguments or {}

        if tool_name == TOOL_NAME_NO_OP:
            return {}
        if tool_name == TOOL_NAME_MOVE_TO_DESTINATION:
            return self._resolve_move_to_destination(args, runtime_context)
        if tool_name == TOOL_NAME_WHISPER:
            return self._resolve_whisper(args, runtime_context)
        if tool_name == TOOL_NAME_SAY:
            return {
                "content": args.get("content", ""),
                "channel": SpeechChannel.SAY,
            }
        if tool_name == TOOL_NAME_INSPECT_ITEM:
            return self._resolve_inspect_item(args, runtime_context)
        if tool_name == TOOL_NAME_INSPECT_TARGET:
            return self._resolve_inspect_target(args, runtime_context)
        if tool_name == TOOL_NAME_INTERACT_WORLD_OBJECT:
            return self._resolve_interact_world_object(args, runtime_context)
        if tool_name == TOOL_NAME_HARVEST_START:
            return self._resolve_harvest_start(args, runtime_context)
        if tool_name == TOOL_NAME_CHANGE_ATTENTION:
            return self._resolve_change_attention(args, runtime_context)
        if tool_name == TOOL_NAME_CONVERSATION_ADVANCE:
            return self._resolve_conversation_advance(args, runtime_context)
        if tool_name == TOOL_NAME_PLACE_OBJECT:
            return self._resolve_place_object(args, runtime_context)
        if tool_name == TOOL_NAME_DESTROY_PLACEABLE:
            return {}
        if tool_name == TOOL_NAME_CHEST_STORE:
            return self._resolve_chest_store(args, runtime_context)
        if tool_name == TOOL_NAME_CHEST_TAKE:
            return self._resolve_chest_take(args, runtime_context)
        if tool_name == TOOL_NAME_COMBAT_USE_SKILL:
            return self._resolve_combat_use_skill(args, runtime_context)
        if tool_name == TOOL_NAME_QUEST_ACCEPT:
            return self._resolve_quest_label(args, runtime_context, "quest_id")
        if tool_name == TOOL_NAME_QUEST_CANCEL:
            return self._resolve_quest_label(args, runtime_context, "quest_id")
        if tool_name == TOOL_NAME_QUEST_APPROVE:
            return self._resolve_quest_label(args, runtime_context, "quest_id")
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
            return self._resolve_trade_label(args, runtime_context)
        if tool_name == TOOL_NAME_TRADE_CANCEL:
            return self._resolve_trade_label(args, runtime_context)
        return dict(args)

    def _resolve_move_to_destination(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("destination_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "移動先ラベルが指定されていません。",
                "INVALID_DESTINATION_LABEL",
            )
        target = self._require_target_type(
            label,
            runtime_context,
            "移動先ラベル",
            (DestinationToolRuntimeTargetDto,),
            invalid_label_code="INVALID_DESTINATION_LABEL",
            invalid_kind_code="INVALID_DESTINATION_KIND",
        )
        if target.spot_id is None:
            raise ToolArgumentResolutionException(
                f"移動先として使えないラベルです: {label}",
                "INVALID_DESTINATION_KIND",
            )
        return {
            "destination_type": target.destination_type or "spot",
            "target_spot_id": target.spot_id,
            "target_location_area_id": target.location_area_id,
        }

    def _resolve_whisper(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "囁き先ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = self._require_target_type(
            label,
            runtime_context,
            "囁き先ラベル",
            (PlayerToolRuntimeTargetDto,),
        )
        if target.player_id is None:
            raise ToolArgumentResolutionException(
                f"囁きはプレイヤー宛てにのみ送れます: {label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "content": args.get("content", ""),
            "channel": SpeechChannel.WHISPER,
            "target_player_id": target.player_id,
        }

    def _resolve_interact_world_object(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "相互作用対象ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = self._require_target_type(
            label,
            runtime_context,
            "相互作用対象ラベル",
            (
                NpcToolRuntimeTargetDto,
                ChestToolRuntimeTargetDto,
                WorldObjectToolRuntimeTargetDto,
            ),
        )
        if target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"相互作用に使えないラベルです: {label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "target_world_object_id": target.world_object_id,
            "target_display_name": target.display_name,
        }

    def _resolve_harvest_start(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "採集対象ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = self._require_target_type(
            label,
            runtime_context,
            "採集対象ラベル",
            (ResourceToolRuntimeTargetDto,),
        )
        if target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"採集に使えないラベルです: {label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "target_world_object_id": target.world_object_id,
            "target_display_name": target.display_name,
        }

    def _resolve_change_attention(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("level_label")
        target = self._require_target_type(
            label,
            runtime_context,
            "注意レベルラベル",
            (AttentionLevelToolRuntimeTargetDto,),
        )
        if target.attention_level_value is None:
            raise ToolArgumentResolutionException(
                f"注意レベル変更に使えないラベルです: {label}",
                "INVALID_TARGET_KIND",
            )
        return {"attention_level_value": target.attention_level_value}

    def _resolve_conversation_advance(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        target_label = args.get("target_label")
        target = self._require_target_type(
            target_label,
            runtime_context,
            "会話対象ラベル",
            (NpcToolRuntimeTargetDto,),
        )
        if target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"会話対象に使えないラベルです: {target_label}",
                "INVALID_TARGET_KIND",
            )
        choice_label = args.get("choice_label")
        choice_index = None
        if choice_label is not None:
            choice_target = self._require_target_type(
                choice_label,
                runtime_context,
                "会話選択肢ラベル",
                (ConversationChoiceToolRuntimeTargetDto,),
            )
            if choice_target.world_object_id != target.world_object_id:
                raise ToolArgumentResolutionException(
                    f"会話相手に対応しない選択肢ラベルです: {choice_label}",
                    "INVALID_TARGET_KIND",
                )
            choice_index = choice_target.conversation_choice_index
        return {
            "npc_world_object_id": target.world_object_id,
            "choice_index": choice_index,
            "target_display_name": target.display_name,
        }

    def _resolve_place_object(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("inventory_item_label")
        target = self._require_target_type(
            label,
            runtime_context,
            "在庫アイテムラベル",
            (InventoryToolRuntimeTargetDto,),
        )
        if target.inventory_slot_id is None or not target.is_placeable:
            raise ToolArgumentResolutionException(
                f"設置に使えない在庫ラベルです: {label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "inventory_slot_id": target.inventory_slot_id,
            "target_display_name": target.display_name,
        }

    def _resolve_inspect_item(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("inventory_item_label")
        target = self._require_target_type(
            label,
            runtime_context,
            "在庫アイテムラベル",
            (InventoryToolRuntimeTargetDto,),
        )
        if target.item_instance_id is None:
            raise ToolArgumentResolutionException(
                f"アイテムとして解決できません: {label}",
                "INVALID_TARGET_KIND",
            )
        return {"item_instance_id": target.item_instance_id}

    def _resolve_inspect_target(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "対象ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = self._require_target_type(
            label,
            runtime_context,
            "対象ラベル",
            (
                MonsterToolRuntimeTargetDto,
                NpcToolRuntimeTargetDto,
                ChestToolRuntimeTargetDto,
                ResourceToolRuntimeTargetDto,
                WorldObjectToolRuntimeTargetDto,
            ),
        )
        if target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"対象として解決できません: {label}",
                "INVALID_TARGET_KIND",
            )
        return {"target_world_object_id": target.world_object_id}

    def _resolve_chest_store(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        chest_label = args.get("target_label")
        chest = self._require_target_type(
            chest_label,
            runtime_context,
            "宝箱ラベル",
            (ChestToolRuntimeTargetDto,),
        )
        if chest.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"宝箱として使えないラベルです: {chest_label}",
                "INVALID_TARGET_KIND",
            )
        item_label = args.get("inventory_item_label")
        item = self._require_target_type(
            item_label,
            runtime_context,
            "在庫アイテムラベル",
            (InventoryToolRuntimeTargetDto,),
        )
        if item.item_instance_id is None:
            raise ToolArgumentResolutionException(
                f"収納に使えない在庫ラベルです: {item_label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "chest_world_object_id": chest.world_object_id,
            "item_instance_id": item.item_instance_id,
            "chest_display_name": chest.display_name,
            "item_display_name": item.display_name,
        }

    def _resolve_chest_take(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        chest_label = args.get("target_label")
        chest = self._require_target_type(
            chest_label,
            runtime_context,
            "宝箱ラベル",
            (ChestToolRuntimeTargetDto,),
        )
        if chest.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"宝箱として使えないラベルです: {chest_label}",
                "INVALID_TARGET_KIND",
            )
        item_label = args.get("chest_item_label")
        item = self._require_target_type(
            item_label,
            runtime_context,
            "チェスト中身ラベル",
            (ChestItemToolRuntimeTargetDto,),
        )
        if item.item_instance_id is None or item.chest_world_object_id != chest.world_object_id:
            raise ToolArgumentResolutionException(
                f"対象の宝箱に対応しない中身ラベルです: {item_label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "chest_world_object_id": chest.world_object_id,
            "item_instance_id": item.item_instance_id,
            "chest_display_name": chest.display_name,
            "item_display_name": item.display_name,
        }

    def _resolve_combat_use_skill(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        skill_label = args.get("skill_label")
        skill = self._require_target_type(
            skill_label,
            runtime_context,
            "スキルラベル",
            (SkillToolRuntimeTargetDto,),
        )
        if skill.skill_loadout_id is None or skill.skill_slot_index is None:
            raise ToolArgumentResolutionException(
                f"スキルとして使えないラベルです: {skill_label}",
                "INVALID_TARGET_KIND",
            )
        resolved: Dict[str, Any] = {
            "skill_loadout_id": skill.skill_loadout_id,
            "skill_slot_index": skill.skill_slot_index,
            "skill_display_name": skill.display_name,
            "auto_aim": True,
        }
        target_label = args.get("target_label")
        if target_label is None:
            return resolved
        target = self._require_target_type(
            target_label,
            runtime_context,
            "攻撃対象ラベル",
            (
                PlayerToolRuntimeTargetDto,
                MonsterToolRuntimeTargetDto,
                NpcToolRuntimeTargetDto,
            ),
        )
        direction = self._resolve_direction_from_context(target, runtime_context)
        resolved["auto_aim"] = False
        resolved["target_direction"] = direction
        resolved["target_display_name"] = target.display_name
        return resolved

    def _require_target(
        self,
        label: Any,
        runtime_context: ToolRuntimeContextDto,
        label_name: str,
        *,
        invalid_label_code: str = "INVALID_TARGET_LABEL",
    ):
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                f"{label_name}が指定されていません。",
                invalid_label_code,
            )
        target = runtime_context.targets.get(label)
        if target is None:
            raise ToolArgumentResolutionException(
                f"指定された対象ラベルは現在の候補にありません: {label}",
                invalid_label_code,
            )
        return target

    def _require_target_type(
        self,
        label: Any,
        runtime_context: ToolRuntimeContextDto,
        label_name: str,
        expected_types: tuple[type[ToolRuntimeTargetDto], ...],
        *,
        invalid_label_code: str = "INVALID_TARGET_LABEL",
        invalid_kind_code: str = "INVALID_TARGET_KIND",
    ) -> ToolRuntimeTargetDto:
        target = self._require_target(
            label,
            runtime_context,
            label_name,
            invalid_label_code=invalid_label_code,
        )
        if not isinstance(target, expected_types):
            raise ToolArgumentResolutionException(
                f"{label_name}として使えないラベルです: {label}",
                invalid_kind_code,
            )
        return target

    def _resolve_quest_label(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
        id_key: str,
    ) -> Dict[str, Any]:
        label = args.get("quest_label")
        target = self._require_target_type(
            label,
            runtime_context,
            "クエストラベル",
            (QuestToolRuntimeTargetDto,),
        )
        if target.quest_id is None:
            raise ToolArgumentResolutionException(
                f"クエストとして解決できません: {label}",
                "INVALID_TARGET_KIND",
            )
        return {"quest_id": target.quest_id}

    def _resolve_guild_label(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
        include_amount: bool = False,
    ) -> Dict[str, Any]:
        label = args.get("guild_label")
        target = self._require_target_type(
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
                result["amount"] = int(amount)
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
            listing_target = self._require_target_type(
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
            shop_target = self._require_target_type(
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
            listing_id = int(listing_id_raw)
        else:
            raise ToolArgumentResolutionException(
                "listing_label または listing_id を指定してください。",
                "INVALID_TARGET_LABEL",
            )
        quantity = args.get("quantity", 1)
        return {
            "shop_id": shop_id,
            "listing_id": listing_id,
            "quantity": int(quantity),
        }

    def _resolve_shop_list_item(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        shop_label = args.get("shop_label")
        shop_target = self._require_target_type(
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
        item_target = self._require_target_type(
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
        return {
            "shop_id": shop_target.shop_id,
            "slot_id": item_target.inventory_slot_id,
            "price_per_unit": int(price),
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
            listing_target = self._require_target_type(
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
            shop_target = self._require_target_type(
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
            return {"shop_id": shop_target.shop_id, "listing_id": int(listing_id_raw)}
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
        item_target = self._require_target_type(
            item_label,
            runtime_context,
            "在庫アイテムラベル",
            (InventoryToolRuntimeTargetDto,),
        )
        if item_target.inventory_slot_id is None or item_target.item_instance_id is None:
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
        slot_id = item_target.inventory_slot_id
        if slot_id is None:
            raise ToolArgumentResolutionException(
                f"出品に使えない在庫ラベルです: {item_label}",
                "INVALID_TARGET_KIND",
            )
        result: Dict[str, Any] = {
            "item_instance_id": item_target.item_instance_id,
            "slot_id": slot_id,
            "requested_gold": int(requested_gold),
        }
        target_player_label = args.get("target_player_label")
        target_player_id = args.get("target_player_id")
        if target_player_label is not None:
            player_target = self._require_target_type(
                target_player_label,
                runtime_context,
                "プレイヤーラベル",
                (PlayerToolRuntimeTargetDto,),
            )
            if player_target.player_id is not None:
                result["target_player_id"] = player_target.player_id
        elif target_player_id is not None:
            result["target_player_id"] = int(target_player_id)
        return result

    def _resolve_trade_label(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("trade_label")
        target = self._require_target_type(
            label,
            runtime_context,
            "取引ラベル",
            (TradeToolRuntimeTargetDto,),
        )
        if target.trade_id is None:
            raise ToolArgumentResolutionException(
                f"取引として解決できません: {label}",
                "INVALID_TARGET_KIND",
            )
        return {"trade_id": target.trade_id}

    def _resolve_direction_from_context(
        self,
        target,
        runtime_context: ToolRuntimeContextDto,
    ) -> str:
        if target.relative_dx is None or target.relative_dy is None:
            raise ToolArgumentResolutionException(
                f"対象の方向を特定できません: {target.label}",
                "INVALID_TARGET_KIND",
            )
        if target.relative_dx == 0 and target.relative_dy == 0:
            raise ToolArgumentResolutionException(
                f"対象の方向を特定できません: {target.label}",
                "INVALID_TARGET_KIND",
            )
        resolved = Facing.from_delta(
            target.relative_dx,
            target.relative_dy,
            target.relative_dz or 0,
        )
        return resolved.to_direction().value
