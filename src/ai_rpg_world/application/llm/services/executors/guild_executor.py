"""
Guild ツール（create, add_member, change_role, disband, leave, deposit_bank, withdraw_bank）の実行。

ToolCommandMapper のサブマッパーとして、ギルド関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    invalid_arg_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_GUILD_ADD_MEMBER,
    TOOL_NAME_GUILD_CHANGE_ROLE,
    TOOL_NAME_GUILD_CREATE,
    TOOL_NAME_GUILD_DEPOSIT_BANK,
    TOOL_NAME_GUILD_DISBAND,
    TOOL_NAME_GUILD_LEAVE,
    TOOL_NAME_GUILD_WITHDRAW_BANK,
)
from ai_rpg_world.application.guild.contracts.commands import (
    AddGuildMemberCommand,
    ChangeGuildRoleCommand,
    CreateGuildCommand,
    DepositToGuildBankCommand,
    DisbandGuildCommand,
    LeaveGuildCommand,
    WithdrawFromGuildBankCommand,
)


class GuildToolExecutor:
    """
    Guild ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返し、
    ToolCommandMapper が _executor_map にマージする。
    """

    def __init__(self, guild_service: Optional[Any] = None) -> None:
        self._guild_service = guild_service

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。guild_service が None の場合は空辞書。"""
        if self._guild_service is None:
            return {}
        return {
            TOOL_NAME_GUILD_CREATE: self._execute_guild_create,
            TOOL_NAME_GUILD_ADD_MEMBER: self._execute_guild_add_member,
            TOOL_NAME_GUILD_CHANGE_ROLE: self._execute_guild_change_role,
            TOOL_NAME_GUILD_DISBAND: self._execute_guild_disband,
            TOOL_NAME_GUILD_LEAVE: self._execute_guild_leave,
            TOOL_NAME_GUILD_DEPOSIT_BANK: self._execute_guild_deposit_bank,
            TOOL_NAME_GUILD_WITHDRAW_BANK: self._execute_guild_withdraw_bank,
        }

    def _execute_guild_create(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
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

    def _execute_guild_add_member(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
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

    def _execute_guild_change_role(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
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

    def _execute_guild_disband(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
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

    def _execute_guild_leave(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
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

    def _execute_guild_deposit_bank(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
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

    def _execute_guild_withdraw_bank(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
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
