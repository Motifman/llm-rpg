"""
World ツール（inspect_item, inspect_target, interact, harvest, place, destroy, drop, chest, change_attention, conversation, combat）の実行。

ToolCommandMapper のサブマッパーとして、ワールド・ゲーム全体に関するツール実行のみを担当する。
"""

from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_DROP_ITEM,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_PLACE_OBJECT,
)
from ai_rpg_world.application.conversation.contracts.commands import AdvanceConversationCommand
from ai_rpg_world.application.conversation.contracts.dtos import AdvanceConversationResultDto
from ai_rpg_world.application.harvest.contracts.dtos import HarvestCommandResultDto
from ai_rpg_world.application.world.contracts.commands import (
    ChangeAttentionLevelCommand,
    InteractWorldObjectCommand,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
    from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
    from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository


class WorldToolExecutor:
    """
    World ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返し、
    ToolCommandMapper が _executor_map にマージする。
    """

    def __init__(
        self,
        interaction_service: Optional[Any] = None,
        harvest_service: Optional[Any] = None,
        attention_service: Optional[Any] = None,
        conversation_service: Optional[Any] = None,
        place_object_service: Optional[Any] = None,
        drop_item_service: Optional[Any] = None,
        chest_service: Optional[Any] = None,
        skill_tool_service: Optional[Any] = None,
        item_repository: Optional["ItemRepository"] = None,
        monster_repository: Optional["MonsterRepository"] = None,
        physical_map_repository: Optional["PhysicalMapRepository"] = None,
        player_status_repository: Optional["PlayerStatusRepository"] = None,
    ) -> None:
        self._interaction_service = interaction_service
        self._harvest_service = harvest_service
        self._attention_service = attention_service
        self._conversation_service = conversation_service
        self._place_object_service = place_object_service
        self._drop_item_service = drop_item_service
        self._chest_service = chest_service
        self._skill_tool_service = skill_tool_service
        self._item_repository = item_repository
        self._monster_repository = monster_repository
        self._physical_map_repository = physical_map_repository
        self._player_status_repository = player_status_repository

    def get_handlers(
        self,
    ) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。"""
        result: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]] = {}
        result[TOOL_NAME_INSPECT_ITEM] = self._execute_inspect_item
        result[TOOL_NAME_INSPECT_TARGET] = self._execute_inspect_target
        result[TOOL_NAME_INTERACT_WORLD_OBJECT] = self._execute_interact_world_object
        result[TOOL_NAME_HARVEST_START] = self._execute_harvest_start
        result[TOOL_NAME_CHANGE_ATTENTION] = self._execute_change_attention
        result[TOOL_NAME_CONVERSATION_ADVANCE] = self._execute_conversation_advance
        result[TOOL_NAME_PLACE_OBJECT] = self._execute_place_object
        result[TOOL_NAME_DESTROY_PLACEABLE] = lambda pid, a: self._execute_destroy_placeable(pid)
        result[TOOL_NAME_DROP_ITEM] = self._execute_drop_item
        result[TOOL_NAME_CHEST_STORE] = self._execute_chest_store
        result[TOOL_NAME_CHEST_TAKE] = self._execute_chest_take
        result[TOOL_NAME_COMBAT_USE_SKILL] = self._execute_combat_use_skill
        return result

    def _execute_change_attention(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._attention_service is None:
            return unknown_tool("注意レベル変更ツールはまだ利用できません。")
        try:
            value = args.get("attention_level_value")
            self._attention_service.change_attention_level(
                ChangeAttentionLevelCommand(
                    player_id=player_id,
                    attention_level=AttentionLevel(value),
                )
            )
            return LlmCommandResultDto(success=True, message="注意レベルを変更しました。")
        except Exception as e:
            return exception_result(e)

    def _execute_conversation_advance(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._conversation_service is None:
            return unknown_tool("会話進行ツールはまだ利用できません。")
        try:
            result: AdvanceConversationResultDto = self._conversation_service.advance_conversation(
                AdvanceConversationCommand(
                    player_id=player_id,
                    npc_id_value=int(args.get("npc_world_object_id")),
                    choice_index=args.get("choice_index"),
                )
            )
            return LlmCommandResultDto(
                success=result.success,
                message=result.message or "会話を進めました。",
            )
        except Exception as e:
            return exception_result(e)

    def _execute_place_object(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._place_object_service is None:
            return unknown_tool("設置ツールはまだ利用できません。")
        try:
            self._place_object_service.place_from_inventory_slot(
                player_id=player_id,
                inventory_slot_id=int(args.get("inventory_slot_id")),
            )
            target_display_name = args.get("target_display_name") or "アイテム"
            return LlmCommandResultDto(success=True, message=f"{target_display_name}を設置しました。")
        except Exception as e:
            return exception_result(e)

    def _execute_destroy_placeable(self, player_id: int) -> LlmCommandResultDto:
        if self._place_object_service is None:
            return unknown_tool("破壊ツールはまだ利用できません。")
        try:
            self._place_object_service.destroy_in_front(player_id=player_id)
            return LlmCommandResultDto(success=True, message="前方の設置物を破壊しました。")
        except Exception as e:
            return exception_result(e)

    def _execute_drop_item(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._drop_item_service is None:
            return unknown_tool("ドロップツールはまだ利用できません。")
        inventory_slot_id_raw = args.get("inventory_slot_id")
        if inventory_slot_id_raw is None:
            return LlmCommandResultDto(
                success=False,
                message="inventory_slot_id が指定されていません。",
                error_code="INVALID_TARGET_LABEL",
                remediation=get_remediation("INVALID_TARGET_LABEL"),
            )
        try:
            slot_id_int = (
                int(inventory_slot_id_raw)
                if isinstance(inventory_slot_id_raw, (int, float, str))
                else None
            )
        except (ValueError, TypeError):
            slot_id_int = None
        if slot_id_int is None:
            return LlmCommandResultDto(
                success=False,
                message="inventory_slot_id は 0 以上の整数で指定してください。",
                error_code="INVALID_TARGET_LABEL",
                remediation=get_remediation("INVALID_TARGET_LABEL"),
            )
        if slot_id_int < 0:
            return LlmCommandResultDto(
                success=False,
                message="inventory_slot_id は 0 以上の整数で指定してください。",
                error_code="INVALID_TARGET_LABEL",
                remediation=get_remediation("INVALID_TARGET_LABEL"),
            )
        try:
            self._drop_item_service.drop_from_slot(
                player_id=player_id,
                inventory_slot_id=slot_id_int,
            )
            target_display_name = args.get("target_display_name") or "アイテム"
            return LlmCommandResultDto(success=True, message=f"{target_display_name}を捨てました。")
        except Exception as e:
            return exception_result(e)

    def _execute_chest_store(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._chest_service is None:
            return unknown_tool("チェスト収納ツールはまだ利用できません。")
        try:
            self._chest_service.store_item_by_target(
                player_id=player_id,
                chest_world_object_id=int(args.get("chest_world_object_id")),
                item_instance_id=int(args.get("item_instance_id")),
            )
            return LlmCommandResultDto(
                success=True,
                message=f"{args.get('item_display_name', 'アイテム')}を{args.get('chest_display_name', '宝箱')}に収納しました。",
            )
        except Exception as e:
            return exception_result(e)

    def _execute_chest_take(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._chest_service is None:
            return unknown_tool("チェスト取得ツールはまだ利用できません。")
        try:
            self._chest_service.take_item_by_target(
                player_id=player_id,
                chest_world_object_id=int(args.get("chest_world_object_id")),
                item_instance_id=int(args.get("item_instance_id")),
            )
            return LlmCommandResultDto(
                success=True,
                message=f"{args.get('chest_display_name', '宝箱')}から{args.get('item_display_name', 'アイテム')}を取り出しました。",
            )
        except Exception as e:
            return exception_result(e)

    def _execute_combat_use_skill(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._skill_tool_service is None:
            return unknown_tool("戦闘スキルツールはまだ利用できません。")
        try:
            self._skill_tool_service.use_skill(
                player_id=player_id,
                skill_loadout_id=int(args.get("skill_loadout_id")),
                skill_slot_index=int(args.get("skill_slot_index")),
                target_direction=args.get("target_direction"),
                auto_aim=bool(args.get("auto_aim", False)),
            )
            target_display_name = args.get("target_display_name")
            message = f"{args.get('skill_display_name', 'スキル')}を使用しました。"
            if isinstance(target_display_name, str) and target_display_name:
                message = f"{target_display_name}に向けて{args.get('skill_display_name', 'スキル')}を使用しました。"
            return LlmCommandResultDto(success=True, message=message)
        except Exception as e:
            return exception_result(e)

    def _execute_inspect_item(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if self._item_repository is None:
            return LlmCommandResultDto(
                success=False,
                message="アイテム調査ツールは利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            from ai_rpg_world.domain.item.exception import ItemInstanceIdValidationException
            from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId

            item_instance_id_raw = args.get("item_instance_id")
            if item_instance_id_raw is None:
                return LlmCommandResultDto(
                    success=False,
                    message="item_instance_id が指定されていません。",
                    error_code="INVALID_TARGET_LABEL",
                    remediation=get_remediation("INVALID_TARGET_LABEL"),
                )
            try:
                raw_int = (
                    int(item_instance_id_raw)
                    if isinstance(item_instance_id_raw, (int, float, str))
                    else None
                )
            except (ValueError, TypeError):
                raw_int = None
            if raw_int is None:
                return LlmCommandResultDto(
                    success=False,
                    message="item_instance_id は正の整数で指定してください。",
                    error_code="INVALID_TARGET_LABEL",
                    remediation=get_remediation("INVALID_TARGET_LABEL"),
                )
            try:
                item_id = ItemInstanceId.create(raw_int)
            except ItemInstanceIdValidationException:
                return LlmCommandResultDto(
                    success=False,
                    message="item_instance_id は正の整数で指定してください。",
                    error_code="INVALID_TARGET_LABEL",
                    remediation=get_remediation("INVALID_TARGET_LABEL"),
                )
            item = self._item_repository.find_by_id(item_id)
            if item is None:
                return LlmCommandResultDto(
                    success=False,
                    message="指定されたアイテムが見つかりません。",
                    error_code="ITEM_NOT_FOUND",
                    remediation=get_remediation("ITEM_NOT_FOUND"),
                )
            description = item.item_spec.description
            return LlmCommandResultDto(success=True, message=description)
        except Exception as e:
            return exception_result(e)

    def _execute_inspect_target(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if (
            self._monster_repository is None
            or self._physical_map_repository is None
            or self._player_status_repository is None
        ):
            return LlmCommandResultDto(
                success=False,
                message="対象調査ツールは利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            from ai_rpg_world.domain.world.exception.map_exception import (
                ObjectNotFoundException,
                WorldObjectIdValidationException,
            )
            from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

            target_id_raw = args.get("target_world_object_id")
            if target_id_raw is None:
                return LlmCommandResultDto(
                    success=False,
                    message="target_world_object_id が指定されていません。",
                    error_code="INVALID_TARGET_LABEL",
                    remediation=get_remediation("INVALID_TARGET_LABEL"),
                )
            try:
                raw_int = (
                    int(target_id_raw)
                    if isinstance(target_id_raw, (int, float, str))
                    else None
                )
            except (ValueError, TypeError):
                raw_int = None
            if raw_int is None:
                return LlmCommandResultDto(
                    success=False,
                    message="target_world_object_id は正の整数で指定してください。",
                    error_code="INVALID_TARGET_LABEL",
                    remediation=get_remediation("INVALID_TARGET_LABEL"),
                )
            try:
                world_object_id = WorldObjectId.create(raw_int)
            except WorldObjectIdValidationException:
                return LlmCommandResultDto(
                    success=False,
                    message="target_world_object_id は正の整数で指定してください。",
                    error_code="INVALID_TARGET_LABEL",
                    remediation=get_remediation("INVALID_TARGET_LABEL"),
                )

            status = self._player_status_repository.find_by_id(PlayerId(player_id))
            if status is None or status.current_spot_id is None:
                return LlmCommandResultDto(
                    success=False,
                    message="プレイヤーの位置を取得できません。",
                    error_code="TARGET_NOT_FOUND",
                    remediation=get_remediation("TARGET_NOT_FOUND"),
                )
            physical_map = self._physical_map_repository.find_by_spot_id(
                status.current_spot_id
            )
            if physical_map is None:
                return LlmCommandResultDto(
                    success=False,
                    message="マップが見つかりません。",
                    error_code="TARGET_NOT_FOUND",
                    remediation=get_remediation("TARGET_NOT_FOUND"),
                )

            monster = self._monster_repository.find_by_world_object_id(world_object_id)
            if monster is not None:
                return LlmCommandResultDto(
                    success=True,
                    message=monster.template.description,
                )

            try:
                obj = physical_map.get_object(world_object_id)
                desc = (obj.interaction_data or {}).get("description")
                if desc is None:
                    desc = ""
                return LlmCommandResultDto(success=True, message=desc or "（説明なし）")
            except ObjectNotFoundException:
                return LlmCommandResultDto(
                    success=False,
                    message="指定された対象が見つかりません。",
                    error_code="TARGET_NOT_FOUND",
                    remediation=get_remediation("TARGET_NOT_FOUND"),
                )
        except Exception as e:
            return exception_result(e)

    def _execute_interact_world_object(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if self._interaction_service is None:
            return LlmCommandResultDto(
                success=False,
                message="相互作用ツールはまだ利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            target_world_object_id = args.get("target_world_object_id")
            self._interaction_service.interact_world_object(
                InteractWorldObjectCommand(
                    player_id=player_id,
                    target_world_object_id=(
                        int(target_world_object_id)
                        if isinstance(target_world_object_id, (int, float))
                        else 0
                    ),
                )
            )
            target_display_name = args.get("target_display_name")
            message = (
                f"{target_display_name}に相互作用しました。"
                if isinstance(target_display_name, str) and target_display_name
                else "対象に相互作用しました。"
            )
            return LlmCommandResultDto(success=True, message=message)
        except Exception as e:
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=error_code,
                remediation=get_remediation(error_code),
            )

    def _execute_harvest_start(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if self._harvest_service is None:
            return LlmCommandResultDto(
                success=False,
                message="採集ツールはまだ利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            target_world_object_id = args.get("target_world_object_id")
            result: HarvestCommandResultDto = self._harvest_service.start_harvest_by_target(
                player_id=player_id,
                target_world_object_id=(
                    int(target_world_object_id)
                    if isinstance(target_world_object_id, (int, float))
                    else 0
                ),
            )
            return LlmCommandResultDto(
                success=result.success,
                message=result.message,
            )
        except Exception as e:
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=error_code,
                remediation=get_remediation(error_code),
            )
