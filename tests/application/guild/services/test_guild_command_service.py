import pytest
from unittest.mock import Mock

from ai_rpg_world.application.guild.services.guild_command_service import GuildCommandService
from ai_rpg_world.application.guild.contracts.commands import (
    CreateGuildCommand,
    AddGuildMemberCommand,
    LeaveGuildCommand,
    ChangeGuildRoleCommand,
)
from ai_rpg_world.application.guild.exceptions.command.guild_command_exception import (
    GuildCreationException,
    GuildNotFoundForCommandException,
    GuildAccessDeniedException,
    GuildCommandException,
)
from ai_rpg_world.application.guild.exceptions.base_exception import GuildSystemErrorException
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_guild_repository import (
    InMemoryGuildRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class TestGuildCommandService:
    """GuildCommandServiceのテスト"""

    @pytest.fixture
    def setup_service(self):
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        data_store = InMemoryDataStore()
        uow = InMemoryUnitOfWork(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )
        guild_repository = InMemoryGuildRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        service = GuildCommandService(
            guild_repository=guild_repository,
            unit_of_work=uow,
        )
        return service, guild_repository, uow

    # --- create_guild ---
    def test_create_guild_success(self, setup_service):
        service, guild_repo, _ = setup_service
        command = CreateGuildCommand(
            name="Adventurers",
            description="We adventure together",
            creator_player_id=1,
        )
        result = service.create_guild(command)
        assert result.success is True
        assert "guild_id" in result.data
        guild_id_val = result.data["guild_id"]
        guild = guild_repo.find_by_id(GuildId(guild_id_val))
        assert guild is not None
        assert guild.name == "Adventurers"
        assert guild.description == "We adventure together"
        assert guild.is_member(PlayerId(1)) is True
        assert guild.get_member(PlayerId(1)).role == GuildRole.LEADER

    def test_create_guild_empty_name_raises(self, setup_service):
        service, _, _ = setup_service
        command = CreateGuildCommand(
            name="   ",
            description="x",
            creator_player_id=1,
        )
        with pytest.raises(GuildCreationException):
            service.create_guild(command)

    def test_create_guild_strips_whitespace(self, setup_service):
        service, guild_repo, _ = setup_service
        command = CreateGuildCommand(
            name="  Guild Name  ",
            description="  Desc  ",
            creator_player_id=1,
        )
        result = service.create_guild(command)
        assert result.success is True
        guild = guild_repo.find_by_id(GuildId(result.data["guild_id"]))
        assert guild.name == "Guild Name"
        assert guild.description == "Desc"

    # --- add_member ---
    def test_add_member_success(self, setup_service):
        service, guild_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(name="G", description="", creator_player_id=1)
        )
        guild_id = create_result.data["guild_id"]
        command = AddGuildMemberCommand(
            guild_id=guild_id,
            inviter_player_id=1,
            new_member_player_id=2,
        )
        result = service.add_member(command)
        assert result.success is True
        guild = guild_repo.find_by_id(GuildId(guild_id))
        assert guild.is_member(PlayerId(2)) is True
        assert guild.get_member(PlayerId(2)).role == GuildRole.MEMBER

    def test_add_member_guild_not_found_raises(self, setup_service):
        service, _, _ = setup_service
        command = AddGuildMemberCommand(
            guild_id=99999,
            inviter_player_id=1,
            new_member_player_id=2,
        )
        with pytest.raises(GuildNotFoundForCommandException):
            service.add_member(command)

    def test_add_member_member_cannot_invite_raises(self, setup_service):
        """MEMBER は招待権限がない（ドメインの InsufficientGuildPermissionException が GuildCommandException にラップされる）"""
        service, guild_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(name="G", description="", creator_player_id=1)
        )
        guild_id = create_result.data["guild_id"]
        service.add_member(
            AddGuildMemberCommand(
                guild_id=guild_id,
                inviter_player_id=1,
                new_member_player_id=2,
            )
        )
        command = AddGuildMemberCommand(
            guild_id=guild_id,
            inviter_player_id=2,
            new_member_player_id=3,
        )
        with pytest.raises(GuildCommandException):
            service.add_member(command)

    # --- leave_guild ---
    def test_leave_guild_success(self, setup_service):
        service, guild_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(name="G", description="", creator_player_id=1)
        )
        guild_id = create_result.data["guild_id"]
        service.add_member(
            AddGuildMemberCommand(
                guild_id=guild_id,
                inviter_player_id=1,
                new_member_player_id=2,
            )
        )
        command = LeaveGuildCommand(guild_id=guild_id, player_id=2)
        result = service.leave_guild(command)
        assert result.success is True
        guild = guild_repo.find_by_id(GuildId(guild_id))
        assert guild.is_member(PlayerId(2)) is False

    def test_leave_guild_guild_not_found_raises(self, setup_service):
        service, _, _ = setup_service
        command = LeaveGuildCommand(guild_id=99999, player_id=1)
        with pytest.raises(GuildNotFoundForCommandException):
            service.leave_guild(command)

    def test_leave_guild_leader_when_only_member_success(self, setup_service):
        service, guild_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(name="G", description="", creator_player_id=1)
        )
        guild_id = create_result.data["guild_id"]
        command = LeaveGuildCommand(guild_id=guild_id, player_id=1)
        result = service.leave_guild(command)
        assert result.success is True
        guild = guild_repo.find_by_id(GuildId(guild_id))
        assert guild is None or not guild.is_member(PlayerId(1))

    # --- change_role ---
    def test_change_role_success(self, setup_service):
        service, guild_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(name="G", description="", creator_player_id=1)
        )
        guild_id = create_result.data["guild_id"]
        service.add_member(
            AddGuildMemberCommand(
                guild_id=guild_id,
                inviter_player_id=1,
                new_member_player_id=2,
            )
        )
        command = ChangeGuildRoleCommand(
            guild_id=guild_id,
            changer_player_id=1,
            target_player_id=2,
            new_role="officer",
        )
        result = service.change_role(command)
        assert result.success is True
        guild = guild_repo.find_by_id(GuildId(guild_id))
        assert guild.get_member(PlayerId(2)).role == GuildRole.OFFICER

    def test_change_role_guild_not_found_raises(self, setup_service):
        service, _, _ = setup_service
        command = ChangeGuildRoleCommand(
            guild_id=99999,
            changer_player_id=1,
            target_player_id=2,
            new_role="member",
        )
        with pytest.raises(GuildNotFoundForCommandException):
            service.change_role(command)

    def test_change_role_invalid_role_raises(self, setup_service):
        service, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(name="G", description="", creator_player_id=1)
        )
        guild_id = create_result.data["guild_id"]
        service.add_member(
            AddGuildMemberCommand(
                guild_id=guild_id,
                inviter_player_id=1,
                new_member_player_id=2,
            )
        )
        command = ChangeGuildRoleCommand(
            guild_id=guild_id,
            changer_player_id=1,
            target_player_id=2,
            new_role="invalid_role",
        )
        with pytest.raises(GuildCommandException):
            service.change_role(command)

    def test_change_role_member_cannot_change_raises(self, setup_service):
        """MEMBER は役職変更権限がない（ドメインの InsufficientGuildPermissionException が GuildCommandException にラップされる）"""
        service, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(name="G", description="", creator_player_id=1)
        )
        guild_id = create_result.data["guild_id"]
        service.add_member(
            AddGuildMemberCommand(
                guild_id=guild_id,
                inviter_player_id=1,
                new_member_player_id=2,
            )
        )
        service.add_member(
            AddGuildMemberCommand(
                guild_id=guild_id,
                inviter_player_id=1,
                new_member_player_id=3,
            )
        )
        command = ChangeGuildRoleCommand(
            guild_id=guild_id,
            changer_player_id=2,
            target_player_id=3,
            new_role="officer",
        )
        with pytest.raises(GuildCommandException):
            service.change_role(command)

    def test_unexpected_exception_wrapped_as_system_error(self, setup_service):
        """想定外の例外は GuildSystemErrorException にラップされる"""
        service, guild_repo, _ = setup_service
        original_error = RuntimeError("database connection failed")
        guild_repo.find_by_id = Mock(side_effect=original_error)
        command = CreateGuildCommand(name="G", description="", creator_player_id=1)
        service.create_guild(command)
        command2 = AddGuildMemberCommand(
            guild_id=1,
            inviter_player_id=1,
            new_member_player_id=2,
        )
        with pytest.raises(GuildSystemErrorException) as exc_info:
            service.add_member(command2)
        assert exc_info.value.original_exception is original_error
