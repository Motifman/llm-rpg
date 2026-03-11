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
from ai_rpg_world.application.llm.services.executors.world_executor import (
    WorldToolExecutor,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_GUILD_ADD_MEMBER,
    TOOL_NAME_GUILD_CHANGE_ROLE,
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_GUILD_LEAVE,
    TOOL_NAME_GUILD_WITHDRAW_BANK,
    TOOL_NAME_NO_OP,
)
from ai_rpg_world.application.speech.services.player_speech_service import (
    PlayerSpeechApplicationService,
)
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)
from ai_rpg_world.application.llm.services.memory_query_executor import (
    MemoryQueryExecutor,
)
from ai_rpg_world.application.llm.services.subagent_runner import SubagentRunner

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
        interaction_service: Optional[Any] = None,
        harvest_service: Optional[Any] = None,
        attention_service: Optional[Any] = None,
        conversation_service: Optional[Any] = None,
        place_object_service: Optional[Any] = None,
        drop_item_service: Optional[Any] = None,
        chest_service: Optional[Any] = None,
        skill_tool_service: Optional[Any] = None,
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
        self._guild_service = guild_service
        self._executor_map: Dict[str, Any] = {
            TOOL_NAME_NO_OP: lambda pid, a: LlmCommandResultDto(success=True, message="何もしませんでした。", was_no_op=True),
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
        world_executor = WorldToolExecutor(
            interaction_service=interaction_service,
            harvest_service=harvest_service,
            attention_service=attention_service,
            conversation_service=conversation_service,
            place_object_service=place_object_service,
            drop_item_service=drop_item_service,
            chest_service=chest_service,
            skill_tool_service=skill_tool_service,
            item_repository=item_repository,
            monster_repository=monster_repository,
            physical_map_repository=physical_map_repository,
            player_status_repository=player_status_repository,
        )
        self._executor_map.update(world_executor.get_handlers())

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
