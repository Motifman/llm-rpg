import logging
from typing import Callable, Any, Optional

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

from ai_rpg_world.application.guild.contracts.commands import (
    CreateGuildCommand,
    AddGuildMemberCommand,
    LeaveGuildCommand,
    ChangeGuildRoleCommand,
)
from ai_rpg_world.application.guild.contracts.dtos import GuildCommandResultDto
from ai_rpg_world.application.guild.exceptions.base_exception import (
    GuildApplicationException,
    GuildSystemErrorException,
)
from ai_rpg_world.application.guild.exceptions.command.guild_command_exception import (
    GuildCommandException,
    GuildCreationException,
    GuildNotFoundForCommandException,
    GuildAccessDeniedException,
)


def _parse_guild_role(s: str) -> GuildRole:
    """コマンドの文字列を GuildRole に変換"""
    try:
        return GuildRole(s.lower())
    except ValueError:
        raise GuildCommandException(f"Invalid guild role: {s}")


class GuildCommandService:
    """ギルドコマンドサービス"""

    def __init__(self, guild_repository: GuildRepository, unit_of_work: UnitOfWork):
        self._guild_repository = guild_repository
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self, operation: Callable[[], Any], context: dict
    ) -> Any:
        try:
            return operation()
        except GuildApplicationException:
            raise
        except DomainException as e:
            raise GuildCommandException(
                str(e),
                user_id=context.get("user_id"),
                guild_id=context.get("guild_id"),
            ) from e
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise GuildSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            ) from e

    def create_guild(self, command: CreateGuildCommand) -> GuildCommandResultDto:
        """ギルドを作成する。作成者がリーダーとして参加する。"""
        return self._execute_with_error_handling(
            operation=lambda: self._create_guild_impl(command),
            context={
                "action": "create_guild",
                "user_id": command.creator_player_id,
            },
        )

    def _create_guild_impl(self, command: CreateGuildCommand) -> GuildCommandResultDto:
        with self._unit_of_work:
            if not command.name.strip():
                raise GuildCreationException(
                    "ギルド名を入力してください",
                    user_id=command.creator_player_id,
                )
            guild_id = self._guild_repository.generate_guild_id()
            creator_id = PlayerId(command.creator_player_id)
            guild = GuildAggregate.create_guild(
                guild_id=guild_id,
                name=command.name.strip(),
                description=command.description.strip(),
                creator_player_id=creator_id,
            )
            self._guild_repository.save(guild)
            self._logger.info("Guild created: guild_id=%s, creator=%s", guild_id.value, creator_id)
            return GuildCommandResultDto(
                success=True,
                message="ギルドを作成しました",
                data={"guild_id": guild_id.value},
            )

    def add_member(self, command: AddGuildMemberCommand) -> GuildCommandResultDto:
        """ギルドにメンバーを追加する（招待。招待者はオフィサー以上）"""
        return self._execute_with_error_handling(
            operation=lambda: self._add_member_impl(command),
            context={
                "action": "add_member",
                "user_id": command.inviter_player_id,
                "guild_id": command.guild_id,
            },
        )

    def _add_member_impl(self, command: AddGuildMemberCommand) -> GuildCommandResultDto:
        with self._unit_of_work:
            guild_id = GuildId(command.guild_id)
            guild = self._guild_repository.find_by_id(guild_id)
            if guild is None:
                raise GuildNotFoundForCommandException(command.guild_id, "add_member")
            inviter_id = PlayerId(command.inviter_player_id)
            new_member_id = PlayerId(command.new_member_player_id)
            guild.add_member(inviter_player_id=inviter_id, new_player_id=new_member_id)
            self._guild_repository.save(guild)
            self._logger.info(
                "Guild member added: guild_id=%s, new_member=%s",
                command.guild_id,
                command.new_member_player_id,
            )
            return GuildCommandResultDto(
                success=True,
                message="メンバーを追加しました",
                data={"guild_id": command.guild_id},
            )

    def leave_guild(self, command: LeaveGuildCommand) -> GuildCommandResultDto:
        """ギルドから脱退する。"""
        return self._execute_with_error_handling(
            operation=lambda: self._leave_guild_impl(command),
            context={
                "action": "leave_guild",
                "user_id": command.player_id,
                "guild_id": command.guild_id,
            },
        )

    def _leave_guild_impl(self, command: LeaveGuildCommand) -> GuildCommandResultDto:
        with self._unit_of_work:
            guild_id = GuildId(command.guild_id)
            guild = self._guild_repository.find_by_id(guild_id)
            if guild is None:
                raise GuildNotFoundForCommandException(command.guild_id, "leave_guild")
            player_id = PlayerId(command.player_id)
            guild.leave(player_id)
            self._guild_repository.save(guild)
            self._logger.info(
                "Guild member left: guild_id=%s, player_id=%s",
                command.guild_id,
                command.player_id,
            )
            return GuildCommandResultDto(
                success=True,
                message="ギルドから脱退しました",
                data={"guild_id": command.guild_id},
            )

    def change_role(self, command: ChangeGuildRoleCommand) -> GuildCommandResultDto:
        """ギルドメンバーの役職を変更する（変更者はオフィサー以上）"""
        return self._execute_with_error_handling(
            operation=lambda: self._change_role_impl(command),
            context={
                "action": "change_role",
                "user_id": command.changer_player_id,
                "guild_id": command.guild_id,
            },
        )

    def _change_role_impl(self, command: ChangeGuildRoleCommand) -> GuildCommandResultDto:
        with self._unit_of_work:
            guild_id = GuildId(command.guild_id)
            guild = self._guild_repository.find_by_id(guild_id)
            if guild is None:
                raise GuildNotFoundForCommandException(command.guild_id, "change_role")
            changer_id = PlayerId(command.changer_player_id)
            target_id = PlayerId(command.target_player_id)
            new_role = _parse_guild_role(command.new_role)
            guild.change_role(
                changer_player_id=changer_id,
                target_player_id=target_id,
                new_role=new_role,
            )
            self._guild_repository.save(guild)
            self._logger.info(
                "Guild role changed: guild_id=%s, target=%s, new_role=%s",
                command.guild_id,
                command.target_player_id,
                command.new_role,
            )
            return GuildCommandResultDto(
                success=True,
                message="役職を変更しました",
                data={"guild_id": command.guild_id},
            )
