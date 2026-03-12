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
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    invalid_arg_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.services.executors.memory_executor import (
    MemoryToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.movement_executor import (
    MovementToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.quest_executor import (
    QuestToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.shop_executor import (
    ShopToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.speech_executor import (
    SpeechToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.todo_executor import (
    TodoToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.trade_executor import (
    TradeToolExecutor,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_DROP_ITEM,
    TOOL_NAME_GUILD_ADD_MEMBER,
    TOOL_NAME_GUILD_CHANGE_ROLE,
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_GUILD_LEAVE,
    TOOL_NAME_GUILD_WITHDRAW_BANK,
    TOOL_NAME_HARVEST_CANCEL,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
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
from ai_rpg_world.application.speech.services.player_speech_service import (
    PlayerSpeechApplicationService,
)
from ai_rpg_world.application.world.contracts.commands import (
    ChangeAttentionLevelCommand,
    InteractWorldObjectCommand,
)
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
from ai_rpg_world.application.world.services.player_drop_item_service import (
    PlayerDropItemApplicationService,
)
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)
from ai_rpg_world.application.llm.services.memory_query_executor import (
    MemoryQueryExecutor,
)
from ai_rpg_world.application.llm.services.subagent_runner import SubagentRunner
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

# Optional domain command services
from ai_rpg_world.application.guild.contracts.commands import (
    AddGuildMemberCommand,
    ChangeGuildRoleCommand,
    CreateGuildCommand,
    DepositToGuildBankCommand,
    DisbandGuildCommand,
    LeaveGuildCommand,
    WithdrawFromGuildBankCommand,
)


class ToolCommandMapper:
    """
    ツール名と引数からコマンドを組み立て、対応するサービスを呼び出して
    LlmCommandResultDto を返す。失敗時は例外を捕捉し、error_code と remediation を付与する。
    """

    def __init__(
        self,
        movement_service: MovementApplicationService,
        pursuit_service: Optional[Any] = None,
        speech_service: Optional[PlayerSpeechApplicationService] = None,
        interaction_service: Optional[InteractionCommandService] = None,
        harvest_service: Optional[PlayerHarvestApplicationService] = None,
        attention_service: Optional[AttentionLevelApplicationService] = None,
        conversation_service: Optional[ConversationCommandService] = None,
        place_object_service: Optional[PlayerPlaceObjectApplicationService] = None,
        drop_item_service: Optional[PlayerDropItemApplicationService] = None,
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
        if pursuit_service is not None and not callable(
            getattr(pursuit_service, "start_pursuit", None)
        ):
            raise TypeError("pursuit_service must have a callable start_pursuit")
        if pursuit_service is not None and not callable(
            getattr(pursuit_service, "cancel_pursuit", None)
        ):
            raise TypeError("pursuit_service must have a callable cancel_pursuit")
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
        if harvest_service is not None and not callable(
            getattr(harvest_service, "cancel_harvest_by_target", None)
        ):
            raise TypeError("harvest_service must have a callable cancel_harvest_by_target")
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
        if drop_item_service is not None and not callable(
            getattr(drop_item_service, "drop_from_slot", None)
        ):
            raise TypeError("drop_item_service must have a callable drop_from_slot")
        if chest_service is not None and not callable(
            getattr(chest_service, "store_item_by_target", None)
        ):
            raise TypeError("chest_service must have a callable store_item_by_target")
        if skill_tool_service is not None and not callable(
            getattr(skill_tool_service, "use_skill", None)
        ):
            raise TypeError("skill_tool_service must have a callable use_skill")
        self._guild_service = guild_service
        self._item_repository = item_repository
        self._monster_repository = monster_repository
        self._physical_map_repository = physical_map_repository
        self._player_status_repository = player_status_repository
        self._interaction_service = interaction_service
        self._harvest_service = harvest_service
        self._attention_service = attention_service
        self._conversation_service = conversation_service
        self._place_object_service = place_object_service
        self._drop_item_service = drop_item_service
        self._chest_service = chest_service
        self._skill_tool_service = skill_tool_service
        self._executor_map: Dict[str, Any] = {
            TOOL_NAME_NO_OP: lambda pid, a: LlmCommandResultDto(success=True, message="何もしませんでした。", was_no_op=True),
            TOOL_NAME_INSPECT_ITEM: self._execute_inspect_item,
            TOOL_NAME_INSPECT_TARGET: self._execute_inspect_target,
            TOOL_NAME_INTERACT_WORLD_OBJECT: self._execute_interact_world_object,
            TOOL_NAME_HARVEST_START: self._execute_harvest_start,
            TOOL_NAME_HARVEST_CANCEL: self._execute_harvest_cancel,
            TOOL_NAME_CHANGE_ATTENTION: self._execute_change_attention,
            TOOL_NAME_CONVERSATION_ADVANCE: self._execute_conversation_advance,
            TOOL_NAME_PLACE_OBJECT: self._execute_place_object,
            TOOL_NAME_DESTROY_PLACEABLE: lambda pid, a: self._execute_destroy_placeable(pid),
            TOOL_NAME_DROP_ITEM: self._execute_drop_item,
            TOOL_NAME_CHEST_STORE: self._execute_chest_store,
            TOOL_NAME_CHEST_TAKE: self._execute_chest_take,
            TOOL_NAME_COMBAT_USE_SKILL: self._execute_combat_use_skill,
            TOOL_NAME_GUILD_CREATE: self._execute_guild_create,
            TOOL_NAME_GUILD_ADD_MEMBER: self._execute_guild_add_member,
            TOOL_NAME_GUILD_CHANGE_ROLE: self._execute_guild_change_role,
            TOOL_NAME_GUILD_DISBAND: self._execute_guild_disband,
            TOOL_NAME_GUILD_LEAVE: self._execute_guild_leave,
            TOOL_NAME_GUILD_DEPOSIT_BANK: self._execute_guild_deposit_bank,
            TOOL_NAME_GUILD_WITHDRAW_BANK: self._execute_guild_withdraw_bank,
        }
        movement_executor = MovementToolExecutor(
            movement_service=movement_service,
            pursuit_service=pursuit_service,
        )
        self._executor_map.update(movement_executor.get_handlers())
        speech_executor = SpeechToolExecutor(speech_service=speech_service)
        self._executor_map.update(speech_executor.get_handlers())
        memory_executor = MemoryToolExecutor(
            memory_query_executor=memory_query_executor,
            subagent_runner=subagent_runner,
            working_memory_store=working_memory_store,
        )
        self._executor_map.update(memory_executor.get_handlers())
        todo_executor = TodoToolExecutor(todo_store)
        self._executor_map.update(todo_executor.get_handlers())
        quest_executor = QuestToolExecutor(quest_service=quest_service)
        self._executor_map.update(quest_executor.get_handlers())
        shop_executor = ShopToolExecutor(shop_service=shop_service)
        self._executor_map.update(shop_executor.get_handlers())
        trade_executor = TradeToolExecutor(trade_service=trade_service)
        self._executor_map.update(trade_executor.get_handlers())

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

    def _execute_change_attention(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
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

    def _execute_conversation_advance(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
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
    
    def _execute_place_object(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
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

    def _execute_drop_item(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
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

    def _execute_chest_store(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
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

    def _execute_chest_take(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
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

    def _execute_combat_use_skill(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
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

    def _execute_harvest_cancel(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if self._harvest_service is None:
            return LlmCommandResultDto(
                success=False,
                message="採集中断ツールはまだ利用できません。",
                error_code="UNKNOWN_TOOL",
                remediation=get_remediation("UNKNOWN_TOOL"),
            )
        try:
            target_world_object_id = args.get("target_world_object_id")
            result: HarvestCommandResultDto = self._harvest_service.cancel_harvest_by_target(
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

    def _execute_guild_create(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return unknown_tool("ギルド作成ツールはまだ利用できません。")
        if args.get("spot_id") is None or args.get("location_area_id") is None:
            return invalid_arg_result("spot_id/location_area_id")
        if args.get("name") is None:
            return invalid_arg_result("name")
        try:
            result = self._guild_service.create_guild(
                CreateGuildCommand(
                    spot_id=int(args["spot_id"]),
                    location_area_id=int(args["location_area_id"]),
                    name=str(args["name"]),
                    description=str(args.get("description", "")),
                    creator_player_id=player_id,
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_guild_add_member(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return unknown_tool("ギルド招待ツールはまだ利用できません。")
        if args.get("guild_id") is None:
            return invalid_arg_result("guild_id")
        if args.get("new_member_player_id") is None:
            return invalid_arg_result("new_member_player_id")
        try:
            result = self._guild_service.add_member(
                AddGuildMemberCommand(
                    guild_id=int(args["guild_id"]),
                    inviter_player_id=player_id,
                    new_member_player_id=int(args["new_member_player_id"]),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_guild_change_role(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return unknown_tool("ギルド役職変更ツールはまだ利用できません。")
        if args.get("guild_id") is None:
            return invalid_arg_result("guild_id")
        if args.get("target_player_id") is None:
            return invalid_arg_result("target_player_id")
        if args.get("new_role") is None:
            return invalid_arg_result("new_role")
        try:
            result = self._guild_service.change_role(
                ChangeGuildRoleCommand(
                    guild_id=int(args["guild_id"]),
                    changer_player_id=player_id,
                    target_player_id=int(args["target_player_id"]),
                    new_role=str(args["new_role"]),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_guild_disband(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return unknown_tool("ギルド解散ツールはまだ利用できません。")
        if args.get("guild_id") is None:
            return invalid_arg_result("guild_id")
        try:
            result = self._guild_service.disband_guild(
                DisbandGuildCommand(guild_id=int(args["guild_id"]), player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_guild_leave(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return unknown_tool("ギルド脱退ツールはまだ利用できません。")
        if args.get("guild_id") is None:
            return invalid_arg_result("guild_id")
        try:
            result = self._guild_service.leave_guild(
                LeaveGuildCommand(guild_id=int(args["guild_id"]), player_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_guild_deposit_bank(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return unknown_tool("ギルド金庫入金ツールはまだ利用できません。")
        if args.get("guild_id") is None:
            return invalid_arg_result("guild_id")
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
            return exception_result(e)

    def _execute_guild_withdraw_bank(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        if self._guild_service is None:
            return unknown_tool("ギルド金庫出金ツールはまだ利用できません。")
        if args.get("guild_id") is None:
            return invalid_arg_result("guild_id")
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
            return exception_result(e)
