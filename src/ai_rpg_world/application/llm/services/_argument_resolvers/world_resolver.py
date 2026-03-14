"""ワールド・会話・採集・チェスト系ツールの引数解決。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    ActiveHarvestToolRuntimeTargetDto,
    AttentionLevelToolRuntimeTargetDto,
    ChestItemToolRuntimeTargetDto,
    ChestToolRuntimeTargetDto,
    ConversationChoiceToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    NpcToolRuntimeTargetDto,
    ResourceToolRuntimeTargetDto,
    WorldObjectToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    require_target_type,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_DROP_ITEM,
    TOOL_NAME_HARVEST_CANCEL,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SAY,
    TOOL_NAME_WHISPER,
)
from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


class WorldArgumentResolver:
    """ワールド・会話・採集・チェスト系ツールの引数解決。"""

    def resolve_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Optional[Dict[str, Any]]:
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
        if tool_name == TOOL_NAME_HARVEST_CANCEL:
            return self._resolve_harvest_cancel(args, runtime_context)
        if tool_name == TOOL_NAME_CHANGE_ATTENTION:
            return self._resolve_change_attention(args, runtime_context)
        if tool_name == TOOL_NAME_CONVERSATION_ADVANCE:
            return self._resolve_conversation_advance(args, runtime_context)
        if tool_name == TOOL_NAME_PLACE_OBJECT:
            return self._resolve_place_object(args, runtime_context)
        if tool_name == TOOL_NAME_DESTROY_PLACEABLE:
            return {}
        if tool_name == TOOL_NAME_DROP_ITEM:
            return self._resolve_drop_item(args, runtime_context)
        if tool_name == TOOL_NAME_CHEST_STORE:
            return self._resolve_chest_store(args, runtime_context)
        if tool_name == TOOL_NAME_CHEST_TAKE:
            return self._resolve_chest_take(args, runtime_context)
        return None

    def _resolve_whisper(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        from ai_rpg_world.application.llm.contracts.dtos import PlayerToolRuntimeTargetDto

        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "囁き先ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target_type(
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
        target = require_target_type(
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
        target = require_target_type(
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

    def _resolve_harvest_cancel(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "採集中断対象ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target_type(
            label,
            runtime_context,
            "採集中断対象ラベル",
            (ActiveHarvestToolRuntimeTargetDto, ResourceToolRuntimeTargetDto),
        )
        if target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"採集中断に使えないラベルです: {label}",
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
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "注意レベルラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target_type(
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
        target = require_target_type(
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
            choice_target = require_target_type(
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
        target = require_target_type(
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

    def _resolve_drop_item(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("inventory_item_label")
        target = require_target_type(
            label,
            runtime_context,
            "在庫アイテムラベル",
            (InventoryToolRuntimeTargetDto,),
        )
        if target.inventory_slot_id is None:
            raise ToolArgumentResolutionException(
                f"捨てられない在庫ラベルです: {label}",
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
        target = require_target_type(
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
        from ai_rpg_world.application.llm.contracts.dtos import MonsterToolRuntimeTargetDto

        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "対象ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target_type(
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
        chest = require_target_type(
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
        item = require_target_type(
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
        chest = require_target_type(
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
        item = require_target_type(
            item_label,
            runtime_context,
            "チェスト中身ラベル",
            (ChestItemToolRuntimeTargetDto,),
        )
        if (
            item.item_instance_id is None
            or item.chest_world_object_id != chest.world_object_id
        ):
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
