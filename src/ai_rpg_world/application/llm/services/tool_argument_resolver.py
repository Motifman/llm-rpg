"""LLM の UI 向けラベル引数を canonical args に解決する。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.contracts.interfaces import IToolArgumentResolver
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SAY,
    TOOL_NAME_WHISPER,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum


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
        target = runtime_context.targets.get(label)
        if target is None:
            raise ToolArgumentResolutionException(
                f"指定された移動先ラベルは現在の候補にありません: {label}",
                "INVALID_DESTINATION_LABEL",
            )
        if target.kind != "destination" or target.spot_id is None:
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
        target = runtime_context.targets.get(label)
        if target is None:
            raise ToolArgumentResolutionException(
                f"指定された対象ラベルは現在の候補にありません: {label}",
                "INVALID_TARGET_LABEL",
            )
        if target.kind != "player" or target.player_id is None:
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
        target = runtime_context.targets.get(label)
        if target is None:
            raise ToolArgumentResolutionException(
                f"指定された対象ラベルは現在の候補にありません: {label}",
                "INVALID_TARGET_LABEL",
            )
        if target.world_object_id is None or target.kind not in {"npc", "chest", "door", "object"}:
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
        target = runtime_context.targets.get(label)
        if target is None:
            raise ToolArgumentResolutionException(
                f"指定された対象ラベルは現在の候補にありません: {label}",
                "INVALID_TARGET_LABEL",
            )
        if target.kind != "resource" or target.world_object_id is None:
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
        target = self._require_target(label, runtime_context, "注意レベルラベル")
        if target.kind != "attention_level" or target.attention_level_value is None:
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
        target = self._require_target(target_label, runtime_context, "会話対象ラベル")
        if target.kind != "npc" or target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"会話対象に使えないラベルです: {target_label}",
                "INVALID_TARGET_KIND",
            )
        choice_label = args.get("choice_label")
        choice_index = None
        if choice_label is not None:
            choice_target = self._require_target(choice_label, runtime_context, "会話選択肢ラベル")
            if (
                choice_target.kind != "conversation_choice"
                or choice_target.world_object_id != target.world_object_id
            ):
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
        target = self._require_target(label, runtime_context, "在庫アイテムラベル")
        if (
            target.kind != "inventory_item"
            or target.inventory_slot_id is None
            or "place_object" not in target.available_interactions
        ):
            raise ToolArgumentResolutionException(
                f"設置に使えない在庫ラベルです: {label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "inventory_slot_id": target.inventory_slot_id,
            "target_display_name": target.display_name,
        }

    def _resolve_chest_store(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        chest_label = args.get("target_label")
        chest = self._require_target(chest_label, runtime_context, "宝箱ラベル")
        if chest.world_object_id is None or chest.kind != "chest":
            raise ToolArgumentResolutionException(
                f"宝箱として使えないラベルです: {chest_label}",
                "INVALID_TARGET_KIND",
            )
        item_label = args.get("inventory_item_label")
        item = self._require_target(item_label, runtime_context, "在庫アイテムラベル")
        if item.kind != "inventory_item" or item.item_instance_id is None:
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
        chest = self._require_target(chest_label, runtime_context, "宝箱ラベル")
        if chest.world_object_id is None or chest.kind != "chest":
            raise ToolArgumentResolutionException(
                f"宝箱として使えないラベルです: {chest_label}",
                "INVALID_TARGET_KIND",
            )
        item_label = args.get("chest_item_label")
        item = self._require_target(item_label, runtime_context, "チェスト中身ラベル")
        if (
            item.kind != "chest_item"
            or item.item_instance_id is None
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

    def _resolve_combat_use_skill(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        skill_label = args.get("skill_label")
        skill = self._require_target(skill_label, runtime_context, "スキルラベル")
        if (
            skill.kind != "skill"
            or skill.skill_loadout_id is None
            or skill.skill_slot_index is None
        ):
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
        target = self._require_target(target_label, runtime_context, "攻撃対象ラベル")
        if target.kind not in {"player", "monster", "npc"}:
            raise ToolArgumentResolutionException(
                f"攻撃対象に使えないラベルです: {target_label}",
                "INVALID_TARGET_KIND",
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
    ):
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                f"{label_name}が指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = runtime_context.targets.get(label)
        if target is None:
            raise ToolArgumentResolutionException(
                f"指定された対象ラベルは現在の候補にありません: {label}",
                "INVALID_TARGET_LABEL",
            )
        return target

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
        resolved = DirectionEnum.from_delta(
            target.relative_dx,
            target.relative_dy,
            target.relative_dz or 0,
        )
        return resolved.value
