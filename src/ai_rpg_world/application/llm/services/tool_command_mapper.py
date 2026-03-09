"""
ツール名＋引数からコマンドを組み立てて実行し、LlmCommandResultDto を返すマッパー。
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ai_rpg_world.application.quest.services.quest_command_service import QuestCommandService
    from ai_rpg_world.application.guild.services.guild_command_service import GuildCommandService
    from ai_rpg_world.application.shop.services.shop_command_service import ShopCommandService
    from ai_rpg_world.application.trade.services.trade_command_service import TradeCommandService
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
    from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
    from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_MEMORY_QUERY,
    TOOL_NAME_SUBAGENT,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
    TOOL_NAME_WORKING_MEMORY_APPEND,
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
from ai_rpg_world.application.conversation.contracts.commands import AdvanceConversationCommand
from ai_rpg_world.application.conversation.contracts.dtos import AdvanceConversationResultDto
from ai_rpg_world.application.conversation.services.conversation_command_service import (
    ConversationCommandService,
)
from ai_rpg_world.application.harvest.contracts.dtos import HarvestCommandResultDto
from ai_rpg_world.application.harvest.services.player_harvest_service import (
    PlayerHarvestApplicationService,
)
from ai_rpg_world.application.skill.services.player_skill_tool_service import (
    PlayerSkillToolApplicationService,
)
from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.application.speech.services.player_speech_service import (
    PlayerSpeechApplicationService,
)
from ai_rpg_world.application.world.contracts.commands import (
    ChangeAttentionLevelCommand,
    InteractWorldObjectCommand,
)
from ai_rpg_world.application.world.contracts.dtos import MoveResultDto
from ai_rpg_world.application.world.contracts.commands import InteractWorldObjectCommand
from ai_rpg_world.application.world.services.attention_level_service import (
    AttentionLevelApplicationService,
)
from ai_rpg_world.application.world.services.interaction_command_service import (
    InteractionCommandService,
)
from ai_rpg_world.application.world.services.player_chest_service import (
    PlayerChestApplicationService,
)
from ai_rpg_world.application.world.services.player_place_object_service import (
    PlayerPlaceObjectApplicationService,
)
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)
from ai_rpg_world.application.llm.exceptions import (
    DslEvaluationException,
    DslParseException,
    InvalidOutputModeException,
)
from ai_rpg_world.application.llm.services.memory_query_executor import (
    MemoryQueryExecutor,
)
from ai_rpg_world.application.llm.services.subagent_runner import SubagentRunner
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

# Optional domain command services
from ai_rpg_world.application.quest.contracts.commands import (
    AcceptQuestCommand,
    ApproveQuestCommand,
    CancelQuestCommand,
)
from ai_rpg_world.application.guild.contracts.commands import (
    DepositToGuildBankCommand,
    LeaveGuildCommand,
    WithdrawFromGuildBankCommand,
)
from ai_rpg_world.application.shop.contracts.commands import (
    ListShopItemCommand,
    PurchaseFromShopCommand,
    UnlistShopItemCommand,
)
from ai_rpg_world.application.trade.contracts.commands import (
    AcceptTradeCommand,
    CancelTradeCommand,
    OfferItemCommand,
)


class ToolCommandMapper:
    """
    ツール名と引数からコマンドを組み立て、対応するサービスを呼び出して
    LlmCommandResultDto を返す。失敗時は例外を捕捉し、error_code と remediation を付与する。
    """

    def __init__(
        self,
        movement_service: MovementApplicationService,
        speech_service: Optional[PlayerSpeechApplicationService] = None,
        interaction_service: Optional[InteractionCommandService] = None,
        harvest_service: Optional[PlayerHarvestApplicationService] = None,
        attention_service: Optional[AttentionLevelApplicationService] = None,
        conversation_service: Optional[ConversationCommandService] = None,
        place_object_service: Optional[PlayerPlaceObjectApplicationService] = None,
        chest_service: Optional[PlayerChestApplicationService] = None,
        skill_tool_service: Optional[PlayerSkillToolApplicationService] = None,
        quest_service: Optional[Any] = None,
        guild_service: Optional[Any] = None,
        shop_service: Optional[Any] = None,
        trade_service: Optional[Any] = None,
        item_repository: Optional["ItemRepository"] = None,
        monster_repository: Optional["MonsterRepository"] = None,
        physical_map_repository: Optional["PhysicalMapRepository"] = None,
        player_status_repository: Optional["PlayerStatusRepository"] = None,
        memory_query_executor: Optional[MemoryQueryExecutor] = None,
        subagent_runner: Optional[SubagentRunner] = None,
        todo_store: Optional[Any] = None,
        working_memory_store: Optional[Any] = None,
    ) -> None:
        move_to_destination = getattr(movement_service, "move_to_destination", None)
        if not callable(move_to_destination):
            raise TypeError("movement_service must have a callable move_to_destination")
        if speech_service is not None and not callable(getattr(speech_service, "speak", None)):
            raise TypeError("speech_service must have a callable speak")
        if interaction_service is not None and not callable(
            getattr(interaction_service, "interact_world_object", None)
        ):
            raise TypeError("interaction_service must have a callable interact_world_object")
        if harvest_service is not None and not callable(
            getattr(harvest_service, "start_harvest_by_target", None)
        ):
            raise TypeError("harvest_service must have a callable start_harvest_by_target")
        if attention_service is not None and not callable(
            getattr(attention_service, "change_attention_level", None)
        ):
            raise TypeError("attention_service must have a callable change_attention_level")
        if conversation_service is not None and not callable(
            getattr(conversation_service, "advance_conversation", None)
        ):
            raise TypeError("conversation_service must have a callable advance_conversation")
        if place_object_service is not None and not callable(
            getattr(place_object_service, "place_from_inventory_slot", None)
        ):
            raise TypeError("place_object_service must have a callable place_from_inventory_slot")
        if chest_service is not None and not callable(
            getattr(chest_service, "store_item_by_target", None)
        ):
            raise TypeError("chest_service must have a callable store_item_by_target")
        if skill_tool_service is not None and not callable(
            getattr(skill_tool_service, "use_skill", None)
        ):
            raise TypeError("skill_tool_service must have a callable use_skill")
        self._memory_query_executor = memory_query_executor
        self._subagent_runner = subagent_runner
        self._todo_store = todo_store
        self._working_memory_store = working_memory_store
        self._quest_service = quest_service
        self._guild_service = guild_service
        self._shop_service = shop_service
        self._trade_service = trade_service
        self._item_repository = item_repository
        self._monster_repository = monster_repository
        self._physical_map_repository = physical_map_repository
        self._player_status_repository = player_status_repository
        self._movement_service = movement_service
        self._speech_service = speech_service
        self._interaction_service = interaction_service
        self._harvest_service = harvest_service
        self._attention_service = attention_service
        self._conversation_service = conversation_service
        self._place_object_service = place_object_service
        self._chest_service = chest_service
        self._skill_tool_service = skill_tool_service
        self._executor_map: Dict[str, Any] = {
            TOOL_NAME_NO_OP: lambda pid, a: LlmCommandResultDto(success=True, message="何もしませんでした。", was_no_op=True),
            TOOL_NAME_MOVE_TO_DESTINATION: self._execute_move_to_destination,
            TOOL_NAME_WHISPER: self._execute_whisper,
            TOOL_NAME_SAY: self._execute_say,
            TOOL_NAME_INSPECT_ITEM: self._execute_inspect_item,
            TOOL_NAME_INSPECT_TARGET: self._execute_inspect_target,
            TOOL_NAME_INTERACT_WORLD_OBJECT: self._execute_interact_world_object,
            TOOL_NAME_HARVEST_START: self._execute_harvest_start,
            TOOL_NAME_CHANGE_ATTENTION: self._execute_change_attention,
            TOOL_NAME_CONVERSATION_ADVANCE: self._execute_conversation_advance,
            TOOL_NAME_PLACE_OBJECT: self._execute_place_object,
            TOOL_NAME_DESTROY_PLACEABLE: lambda pid, a: self._execute_destroy_placeable(pid),
            TOOL_NAME_CHEST_STORE: self._execute_chest_store,
            TOOL_NAME_CHEST_TAKE: self._execute_chest_take,
            TOOL_NAME_COMBAT_USE_SKILL: self._execute_combat_use_skill,
            TOOL_NAME_QUEST_ACCEPT: self._execute_quest_accept,
            TOOL_NAME_QUEST_CANCEL: self._execute_quest_cancel,
            TOOL_NAME_QUEST_APPROVE: self._execute_quest_approve,
            TOOL_NAME_GUILD_LEAVE: self._execute_guild_leave,
            TOOL_NAME_GUILD_DEPOSIT_BANK: self._execute_guild_deposit_bank,
            TOOL_NAME_GUILD_WITHDRAW_BANK: self._execute_guild_withdraw_bank,
            TOOL_NAME_SHOP_PURCHASE: self._execute_shop_purchase,
            TOOL_NAME_SHOP_LIST_ITEM: self._execute_shop_list_item,
            TOOL_NAME_SHOP_UNLIST_ITEM: self._execute_shop_unlist_item,
            TOOL_NAME_TRADE_OFFER: self._execute_trade_offer,
            TOOL_NAME_TRADE_ACCEPT: self._execute_trade_accept,
            TOOL_NAME_TRADE_CANCEL: self._execute_trade_cancel,
        }
        if memory_query_executor is not None:
            self._executor_map[TOOL_NAME_MEMORY_QUERY] = self._execute_memory_query
        if subagent_runner is not None:
            self._executor_map[TOOL_NAME_SUBAGENT] = self._execute_subagent
        if todo_store is not None:
            self._executor_map[TOOL_NAME_TODO_ADD] = self._execute_todo_add
            self._executor_map[TOOL_NAME_TODO_LIST] = self._execute_todo_list
            self._executor_map[TOOL_NAME_TODO_COMPLETE] = self._execute_todo_complete
        if working_memory_store is not None:
            self._executor_map[TOOL_NAME_WORKING_MEMORY_APPEND] = (
                self._execute_working_memory_append
            )

    def execute(
        self,
        player_id: int,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> LlmCommandResultDto:
        """
        ツールを実行し、結果を LlmCommandResultDto で返す。
        arguments は LLM の function call から渡される辞書（None の場合は {} として扱う）。
        """
        if not isinstance(player_id, int):
            raise TypeError("player_id must be int")
        if player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if not isinstance(tool_name, str):
            raise TypeError("tool_name must be str")
        if arguments is not None and not isinstance(arguments, dict):
            raise TypeError("arguments must be dict or None")
        args = arguments if arguments is not None else {}

        executor = self._executor_map.get(tool_name)
        if executor is not None:
            return executor(player_id, args)
        return LlmCommandResultDto(
            success=False,
            message="未知のツールです。",
            error_code="UNKNOWN_TOOL",
            remediation=get_remediation("UNKNOWN_TOOL"),
        )

    def _execute_move_to_destination(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        try:
            destination_type = args.get("destination_type")
            target_spot_id = args.get("target_spot_id")
            target_location_area_id = args.get("target_location_area_id")
            target_spot_id_int = int(target_spot_id) if isinstance(target_spot_id, (int, float)) else 0
            target_location_area_id_opt: Optional[int] = None
            if destination_type == "location" and target_location_area_id is not None:
                target_location_area_id_opt = (
                    int(target_location_area_id)
                    if isinstance(target_location_area_id, (int, float))
                    else None
                )
            result: MoveResultDto = self._movement_service.move_to_destination(
                player_id=player_id,
                destination_type=destination_type,  # type: ignore[arg-type]
                target_spot_id=target_spot_id_int,
                target_location_area_id=target_location_area_id_opt,
            )
            return LlmCommandResultDto(
                success=result.success,
                message=result.message if result.success else (result.error_message or result.message),
            )
        except Exception as e:
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=error_code,
                remediation=get_remediation(error_code),
            )

    def _execute_change_attention(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._attention_service is None:
            return self._unknown_tool("注意レベル変更ツールはまだ利用できません。")
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
            return self._exception_result(e)

    def _execute_conversation_advance(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._conversation_service is None:
            return self._unknown_tool("会話進行ツールはまだ利用できません。")
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
            return self._exception_result(e)
    
    def _execute_place_object(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._place_object_service is None:
            return self._unknown_tool("設置ツールはまだ利用できません。")
        try:
            self._place_object_service.place_from_inventory_slot(
                player_id=player_id,
                inventory_slot_id=int(args.get("inventory_slot_id")),
            )
            target_display_name = args.get("target_display_name") or "アイテム"
            return LlmCommandResultDto(success=True, message=f"{target_display_name}を設置しました。")
        except Exception as e:
            return self._exception_result(e)

    def _execute_destroy_placeable(self, player_id: int) -> LlmCommandResultDto:
        if self._place_object_service is None:
            return self._unknown_tool("破壊ツールはまだ利用できません。")
        try:
            self._place_object_service.destroy_in_front(player_id=player_id)
            return LlmCommandResultDto(success=True, message="前方の設置物を破壊しました。")
        except Exception as e:
            return self._exception_result(e)

    def _execute_chest_store(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._chest_service is None:
            return self._unknown_tool("チェスト収納ツールはまだ利用できません。")
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
            return self._exception_result(e)

    def _execute_chest_take(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._chest_service is None:
            return self._unknown_tool("チェスト取得ツールはまだ利用できません。")
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
            return self._exception_result(e)

    def _execute_combat_use_skill(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._skill_tool_service is None:
            return self._unknown_tool("戦闘スキルツールはまだ利用できません。")
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
            return self._exception_result(e)

    def _execute_say(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if self._speech_service is None:
            return LlmCommandResultDto(
                success=False,
                message="発言ツールはまだ利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            content = args.get("content", "")
            self._speech_service.speak(
                SpeakCommand(
                    speaker_player_id=player_id,
                    content=content if isinstance(content, str) else str(content),
                    channel=args.get("channel"),
                )
            )
            return LlmCommandResultDto(
                success=True,
                message="発言しました。",
            )
        except Exception as e:
            return self._exception_result(e)

    def _unknown_tool(self, message: str) -> LlmCommandResultDto:
        return LlmCommandResultDto(
            success=False,
            message=message,
            error_code="UNKNOWN_TOOL",
            remediation=get_remediation("UNKNOWN_TOOL"),
        )

    def _exception_result(self, e: Exception) -> LlmCommandResultDto:
        error_code = getattr(e, "error_code", "SYSTEM_ERROR")
        return LlmCommandResultDto(
            success=False,
            message=str(e),
            error_code=error_code,
            remediation=get_remediation(error_code),
        )

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
                raw_int = int(item_instance_id_raw) if isinstance(item_instance_id_raw, (int, float, str)) else None
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
            return self._exception_result(e)

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
                raw_int = int(target_id_raw) if isinstance(target_id_raw, (int, float, str)) else None
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
            physical_map = self._physical_map_repository.find_by_spot_id(status.current_spot_id)
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
            return self._exception_result(e)

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

    def _execute_quest_accept(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._quest_service is None:
            return self._unknown_tool("クエスト受託ツールはまだ利用できません。")
        try:
            result = self._quest_service.accept_quest(
                AcceptQuestCommand(quest_id=int(args["quest_id"]), player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return self._exception_result(e)

    def _execute_quest_cancel(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._quest_service is None:
            return self._unknown_tool("クエストキャンセルツールはまだ利用できません。")
        try:
            result = self._quest_service.cancel_quest(
                CancelQuestCommand(quest_id=int(args["quest_id"]), player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return self._exception_result(e)

    def _execute_quest_approve(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._quest_service is None:
            return self._unknown_tool("クエスト承認ツールはまだ利用できません。")
        try:
            result = self._quest_service.approve_quest(
                ApproveQuestCommand(quest_id=int(args["quest_id"]), approver_player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return self._exception_result(e)

    def _execute_guild_leave(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return self._unknown_tool("ギルド脱退ツールはまだ利用できません。")
        try:
            result = self._guild_service.leave_guild(
                LeaveGuildCommand(guild_id=int(args["guild_id"]), player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return self._exception_result(e)

    def _execute_guild_deposit_bank(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return self._unknown_tool("ギルド金庫入金ツールはまだ利用できません。")
        try:
            result = self._guild_service.deposit_to_guild_bank(
                DepositToGuildBankCommand(
                    guild_id=int(args["guild_id"]),
                    player_id=player_id,
                    amount=int(args.get("amount", 0)),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return self._exception_result(e)

    def _execute_guild_withdraw_bank(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return self._unknown_tool("ギルド金庫出金ツールはまだ利用できません。")
        try:
            result = self._guild_service.withdraw_from_guild_bank(
                WithdrawFromGuildBankCommand(
                    guild_id=int(args["guild_id"]),
                    player_id=player_id,
                    amount=int(args.get("amount", 0)),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return self._exception_result(e)

    def _execute_shop_purchase(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._shop_service is None:
            return self._unknown_tool("ショップ購入ツールはまだ利用できません。")
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
            return self._exception_result(e)

    def _execute_shop_list_item(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._shop_service is None:
            return self._unknown_tool("ショップ出品ツールはまだ利用できません。")
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
            return self._exception_result(e)

    def _execute_shop_unlist_item(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._shop_service is None:
            return self._unknown_tool("ショップ取り下げツールはまだ利用できません。")
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
            return self._exception_result(e)

    def _execute_trade_offer(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._trade_service is None:
            return self._unknown_tool("取引出品ツールはまだ利用できません。")
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
            return self._exception_result(e)

    def _execute_trade_accept(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._trade_service is None:
            return self._unknown_tool("取引受諾ツールはまだ利用できません。")
        try:
            result = self._trade_service.accept_trade(
                AcceptTradeCommand(trade_id=int(args["trade_id"]), buyer_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return self._exception_result(e)

    def _execute_trade_cancel(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._trade_service is None:
            return self._unknown_tool("取引キャンセルツールはまだ利用できません。")
        try:
            result = self._trade_service.cancel_trade(
                CancelTradeCommand(trade_id=int(args["trade_id"]), player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return self._exception_result(e)

    def _execute_memory_query(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._memory_query_executor is None:
            return self._unknown_tool("memory_query ツールはまだ利用できません。")
        try:
            expr = args.get("expr", "").strip()
            if not expr:
                return LlmCommandResultDto(
                    success=False,
                    message="expr が指定されていません。",
                    error_code="MEMORY_QUERY_DSL_PARSE_ERROR",
                    remediation=get_remediation("MEMORY_QUERY_DSL_PARSE_ERROR"),
                )
            output_mode = args.get("output_mode") or "text"
            result = self._memory_query_executor.execute(
                PlayerId(player_id), expr, output_mode
            )
            if "handle_id" in result:
                h_id = result.get("handle_id", "")
                count = result.get("count", "0")
                msg = (
                    f"handle_id: {h_id} (件数: {count}). "
                    f"subagent の bindings で handle:{h_id} として使用できます。"
                )
            else:
                msg = result.get("result") or result.get("count") or "（0件）"
            return LlmCommandResultDto(success=True, message=str(msg))
        except (DslParseException, DslEvaluationException, InvalidOutputModeException) as e:
            return self._exception_result(e)
        except Exception as e:
            return self._exception_result(e)

    def _execute_subagent(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._subagent_runner is None:
            return self._unknown_tool("subagent ツールはまだ利用できません。")
        try:
            bindings = args.get("bindings") or {}
            if not isinstance(bindings, dict):
                bindings = {}
            query = args.get("query", "").strip()
            if not query:
                return LlmCommandResultDto(
                    success=False,
                    message="query が指定されていません。",
                    error_code="SUBAGENT_ERROR",
                    remediation="query を指定してください。",
                )
            dto = self._subagent_runner.run(
                PlayerId(player_id), bindings, query
            )
            msg = dto.answer_summary
            if dto.truncation_note:
                msg = msg + "\n（注: " + dto.truncation_note + "）"
            return LlmCommandResultDto(success=True, message=msg)
        except Exception as e:
            return self._exception_result(e)

    def _execute_todo_add(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._todo_store is None:
            return self._unknown_tool("TODO ツールはまだ利用できません。")
        try:
            content = (args.get("content") or "").strip()
            if not content:
                return LlmCommandResultDto(
                    success=False,
                    message="content が指定されていません。",
                    error_code="TODO_ERROR",
                    remediation="TODO の内容を指定してください。",
                )
            todo_id = self._todo_store.add(PlayerId(player_id), content)
            return LlmCommandResultDto(
                success=True,
                message=f"TODO を追加しました（ID: {todo_id}）。",
            )
        except Exception as e:
            return self._exception_result(e)

    def _execute_todo_list(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._todo_store is None:
            return self._unknown_tool("TODO ツールはまだ利用できません。")
        try:
            entries = self._todo_store.list_uncompleted(PlayerId(player_id))
            if not entries:
                return LlmCommandResultDto(
                    success=True,
                    message="未完了の TODO はありません。",
                )
            lines = [
                f"- [{e.id}] {e.content} (追加: {e.added_at.strftime('%Y-%m-%d %H:%M')})"
                for e in entries
            ]
            return LlmCommandResultDto(
                success=True,
                message="未完了の TODO:\n" + "\n".join(lines),
            )
        except Exception as e:
            return self._exception_result(e)

    def _execute_todo_complete(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._todo_store is None:
            return self._unknown_tool("TODO ツールはまだ利用できません。")
        try:
            todo_id = (args.get("todo_id") or "").strip()
            if not todo_id:
                return LlmCommandResultDto(
                    success=False,
                    message="todo_id が指定されていません。",
                    error_code="TODO_ERROR",
                    remediation="完了する TODO の ID を指定してください。",
                )
            ok = self._todo_store.complete(PlayerId(player_id), todo_id)
            if ok:
                return LlmCommandResultDto(
                    success=True,
                    message=f"TODO {todo_id} を完了にしました。",
                )
            return LlmCommandResultDto(
                success=False,
                message=f"TODO {todo_id} が見つかりません。",
                error_code="TODO_ERROR",
                remediation="正しい todo_id を指定してください。todo_list で一覧を確認できます。",
            )
        except Exception as e:
            return self._exception_result(e)

    def _execute_working_memory_append(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._working_memory_store is None:
            return self._unknown_tool("作業メモツールはまだ利用できません。")
        try:
            text = (args.get("text") or "").strip()
            if not text:
                return LlmCommandResultDto(
                    success=False,
                    message="text が指定されていません。",
                    error_code="WORKING_MEMORY_ERROR",
                    remediation="追加するテキストを指定してください。",
                )
            self._working_memory_store.append(PlayerId(player_id), text)
            return LlmCommandResultDto(
                success=True,
                message="作業メモに追加しました。",
            )
        except Exception as e:
            return self._exception_result(e)

    def _execute_whisper(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if self._speech_service is None:
            return LlmCommandResultDto(
                success=False,
                message="囁きツールはまだ利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            target_player_id = args.get("target_player_id")
            content = args.get("content", "")
            self._speech_service.speak(
                SpeakCommand(
                    speaker_player_id=player_id,
                    content=content if isinstance(content, str) else str(content),
                    channel=args.get("channel"),
                    target_player_id=(
                        int(target_player_id)
                        if isinstance(target_player_id, (int, float))
                        else None
                    ),
                )
            )
            return LlmCommandResultDto(
                success=True,
                message="囁きを送信しました。",
            )
        except Exception as e:
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=error_code,
                remediation=get_remediation(error_code),
            )
