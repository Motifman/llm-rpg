import pytest
from unittest.mock import Mock

from ai_rpg_world.application.guild.services.guild_command_service import GuildCommandService
from ai_rpg_world.application.guild.contracts.commands import (
    CreateGuildCommand,
    AddGuildMemberCommand,
    LeaveGuildCommand,
    ChangeGuildRoleCommand,
    DepositToGuildBankCommand,
    WithdrawFromGuildBankCommand,
    DisbandGuildCommand,
)
from ai_rpg_world.application.guild.exceptions.command.guild_command_exception import (
    GuildCreationException,
    GuildNotFoundForCommandException,
    GuildAccessDeniedException,
    GuildCommandException,
    GuildBankNotFoundForCommandException,
    InsufficientGuildBankBalanceForCommandException,
)
from ai_rpg_world.application.guild.exceptions.base_exception import GuildSystemErrorException
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_guild_repository import (
    InMemoryGuildRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_guild_bank_repository import (
    InMemoryGuildBankRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_location_establishment_repository import (
    InMemoryLocationEstablishmentRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)

# テスト用の共通ロケーション（1ロケーション1ギルドの検証用）
TEST_SPOT_ID = 1
TEST_LOCATION_AREA_ID = 1


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
        guild_bank_repository = InMemoryGuildBankRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        location_establishment_repository = InMemoryLocationEstablishmentRepository(
            data_store=data_store,
            unit_of_work=uow,
        )
        player_status_repository = Mock()
        service = GuildCommandService(
            guild_repository=guild_repository,
            guild_bank_repository=guild_bank_repository,
            player_status_repository=player_status_repository,
            location_establishment_repository=location_establishment_repository,
            unit_of_work=uow,
        )
        return service, guild_repository, guild_bank_repository, uow

    # --- create_guild ---
    def test_create_guild_success(self, setup_service):
        service, guild_repo, _, _ = setup_service
        command = CreateGuildCommand(
            spot_id=TEST_SPOT_ID,
            location_area_id=TEST_LOCATION_AREA_ID,
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
        service, _, _, _ = setup_service
        command = CreateGuildCommand(
            spot_id=TEST_SPOT_ID,
            location_area_id=TEST_LOCATION_AREA_ID,
            name="   ",
            description="x",
            creator_player_id=1,
        )
        with pytest.raises(GuildCreationException):
            service.create_guild(command)

    def test_create_guild_strips_whitespace(self, setup_service):
        service, guild_repo, _, _ = setup_service
        command = CreateGuildCommand(
            spot_id=TEST_SPOT_ID,
            location_area_id=TEST_LOCATION_AREA_ID,
            name="  Guild Name  ",
            description="  Desc  ",
            creator_player_id=1,
        )
        result = service.create_guild(command)
        assert result.success is True
        guild = guild_repo.find_by_id(GuildId(result.data["guild_id"]))
        assert guild.name == "Guild Name"
        assert guild.description == "Desc"

    def test_create_guild_duplicate_location_raises(self, setup_service):
        """同一 spot/location で2回 create_guild すると2回目は GuildCreationException"""
        service, guild_repo, _, _ = setup_service
        cmd = CreateGuildCommand(
            spot_id=TEST_SPOT_ID,
            location_area_id=TEST_LOCATION_AREA_ID,
            name="First",
            description="",
            creator_player_id=1,
        )
        service.create_guild(cmd)
        cmd2 = CreateGuildCommand(
            spot_id=TEST_SPOT_ID,
            location_area_id=TEST_LOCATION_AREA_ID,
            name="Second",
            description="",
            creator_player_id=2,
        )
        with pytest.raises(GuildCreationException):
            service.create_guild(cmd2)

    def test_create_guild_after_disband_same_location_success(self, setup_service):
        """解散後に同じロケーションで create_guild が成功すること"""
        service, guild_repo, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(
                spot_id=TEST_SPOT_ID,
                location_area_id=TEST_LOCATION_AREA_ID,
                name="G",
                description="",
                creator_player_id=1,
            )
        )
        guild_id = create_result.data["guild_id"]
        service.disband_guild(DisbandGuildCommand(guild_id=guild_id, player_id=1))
        create_result2 = service.create_guild(
            CreateGuildCommand(
                spot_id=TEST_SPOT_ID,
                location_area_id=TEST_LOCATION_AREA_ID,
                name="G2",
                description="",
                creator_player_id=1,
            )
        )
        assert create_result2.success is True
        assert create_result2.data["guild_id"] != guild_id
        guild = guild_repo.find_by_id(GuildId(create_result2.data["guild_id"]))
        assert guild.name == "G2"

    # --- add_member ---
    def test_add_member_success(self, setup_service):
        service, guild_repo, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
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
        service, _, _, _ = setup_service
        command = AddGuildMemberCommand(
            guild_id=99999,
            inviter_player_id=1,
            new_member_player_id=2,
        )
        with pytest.raises(GuildNotFoundForCommandException):
            service.add_member(command)

    def test_add_member_member_cannot_invite_raises(self, setup_service):
        """MEMBER は招待権限がない（ドメインの InsufficientGuildPermissionException が GuildCommandException にラップされる）"""
        service, guild_repo, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
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
        service, guild_repo, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
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
        service, _, _, _ = setup_service
        command = LeaveGuildCommand(guild_id=99999, player_id=1)
        with pytest.raises(GuildNotFoundForCommandException):
            service.leave_guild(command)

    def test_leave_guild_leader_when_only_member_success(self, setup_service):
        service, guild_repo, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id = create_result.data["guild_id"]
        command = LeaveGuildCommand(guild_id=guild_id, player_id=1)
        result = service.leave_guild(command)
        assert result.success is True
        guild = guild_repo.find_by_id(GuildId(guild_id))
        assert guild is None or not guild.is_member(PlayerId(1))

    # --- change_role ---
    def test_change_role_success(self, setup_service):
        service, guild_repo, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
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
        service, _, _, _ = setup_service
        command = ChangeGuildRoleCommand(
            guild_id=99999,
            changer_player_id=1,
            target_player_id=2,
            new_role="member",
        )
        with pytest.raises(GuildNotFoundForCommandException):
            service.change_role(command)

    def test_change_role_invalid_role_raises(self, setup_service):
        service, _, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
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
        service, _, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
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
        service, guild_repo, _, _ = setup_service
        original_error = RuntimeError("database connection failed")
        guild_repo.find_by_id = Mock(side_effect=original_error)
        command = CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        service.create_guild(command)
        command2 = AddGuildMemberCommand(
            guild_id=1,
            inviter_player_id=1,
            new_member_player_id=2,
        )
        with pytest.raises(GuildSystemErrorException) as exc_info:
            service.add_member(command2)
        assert exc_info.value.original_exception is original_error

    # --- create_guild creates bank (Phase 5) ---
    def test_create_guild_creates_bank(self, setup_service):
        """ギルド作成時に金庫も作成され、残高 0 であること"""
        service, guild_repo, bank_repo, _ = setup_service
        result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id = GuildId(result.data["guild_id"])
        bank = bank_repo.find_by_id(guild_id)
        assert bank is not None
        assert bank.guild_id == guild_id
        assert bank.gold.value == 0

    # --- deposit_to_guild_bank (Phase 5) ---
    def test_deposit_to_guild_bank_success(self, setup_service):
        """メンバーが金庫に入金できること（プレイヤーゴールドはモックで差し引く）"""
        service, guild_repo, bank_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id_val = create_result.data["guild_id"]
        mock_status = Mock()
        mock_status.pay_gold = Mock()
        service._player_status_repository.find_by_id = Mock(return_value=mock_status)
        service._player_status_repository.save = Mock()
        command = DepositToGuildBankCommand(
            guild_id=guild_id_val,
            player_id=1,
            amount=100,
        )
        result = service.deposit_to_guild_bank(command)
        assert result.success is True
        assert result.data["amount"] == 100
        bank = bank_repo.find_by_id(GuildId(guild_id_val))
        assert bank.gold.value == 100
        mock_status.pay_gold.assert_called_once_with(100)

    def test_deposit_to_guild_bank_guild_not_found_raises(self, setup_service):
        """存在しないギルドへの入金は GuildNotFoundForCommandException"""
        service, _, _, _ = setup_service
        service._player_status_repository.find_by_id = Mock(return_value=Mock(pay_gold=Mock()))
        command = DepositToGuildBankCommand(
            guild_id=99999,
            player_id=1,
            amount=100,
        )
        with pytest.raises(GuildNotFoundForCommandException):
            service.deposit_to_guild_bank(command)

    def test_deposit_to_guild_bank_not_member_raises(self, setup_service):
        """非メンバーは入金できない"""
        service, guild_repo, _, _ = setup_service
        service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id = 1
        command = DepositToGuildBankCommand(
            guild_id=guild_id,
            player_id=999,
            amount=100,
        )
        with pytest.raises(GuildAccessDeniedException):
            service.deposit_to_guild_bank(command)

    # --- withdraw_from_guild_bank (Phase 5) ---
    def test_withdraw_from_guild_bank_success(self, setup_service):
        """オフィサーが金庫から出金できること"""
        service, guild_repo, bank_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id_val = create_result.data["guild_id"]
        service.add_member(AddGuildMemberCommand(guild_id=guild_id_val, inviter_player_id=1, new_member_player_id=2))
        service.change_role(ChangeGuildRoleCommand(guild_id=guild_id_val, changer_player_id=1, target_player_id=2, new_role="officer"))
        bank = bank_repo.find_by_id(GuildId(guild_id_val))
        bank.deposit_gold(200, PlayerId(1))
        bank_repo.save(bank)
        mock_status = Mock()
        mock_status.earn_gold = Mock()
        service._player_status_repository.find_by_id = Mock(return_value=mock_status)
        service._player_status_repository.save = Mock()
        command = WithdrawFromGuildBankCommand(
            guild_id=guild_id_val,
            player_id=2,
            amount=50,
        )
        result = service.withdraw_from_guild_bank(command)
        assert result.success is True
        assert result.data["amount"] == 50
        bank = bank_repo.find_by_id(GuildId(guild_id_val))
        assert bank.gold.value == 150
        mock_status.earn_gold.assert_called_once_with(50)

    def test_withdraw_from_guild_bank_member_cannot_withdraw_raises(self, setup_service):
        """メンバー（オフィサーでない）は出金できない"""
        service, guild_repo, bank_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id_val = create_result.data["guild_id"]
        service.add_member(AddGuildMemberCommand(guild_id=guild_id_val, inviter_player_id=1, new_member_player_id=2))
        bank = bank_repo.find_by_id(GuildId(guild_id_val))
        bank.deposit_gold(100, PlayerId(1))
        bank_repo.save(bank)
        command = WithdrawFromGuildBankCommand(
            guild_id=guild_id_val,
            player_id=2,
            amount=50,
        )
        with pytest.raises(GuildAccessDeniedException):
            service.withdraw_from_guild_bank(command)

    def test_withdraw_from_guild_bank_insufficient_balance_raises(self, setup_service):
        """残高不足では出金できない"""
        service, guild_repo, bank_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id_val = create_result.data["guild_id"]
        mock_status = Mock()
        mock_status.earn_gold = Mock()
        service._player_status_repository.find_by_id = Mock(return_value=mock_status)
        service._player_status_repository.save = Mock()
        command = WithdrawFromGuildBankCommand(
            guild_id=guild_id_val,
            player_id=1,
            amount=100,
        )
        with pytest.raises(InsufficientGuildBankBalanceForCommandException):
            service.withdraw_from_guild_bank(command)

    # --- disband_guild (Phase 5) ---
    def test_disband_guild_success(self, setup_service):
        """リーダーがギルドを解散できること（ギルドと金庫が削除される）"""
        service, guild_repo, bank_repo, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id_val = create_result.data["guild_id"]
        command = DisbandGuildCommand(guild_id=guild_id_val, player_id=1)
        result = service.disband_guild(command)
        assert result.success is True
        assert guild_repo.find_by_id(GuildId(guild_id_val)) is None
        assert bank_repo.find_by_id(GuildId(guild_id_val)) is None

    def test_disband_guild_non_leader_raises(self, setup_service):
        """リーダー以外は解散できない"""
        service, guild_repo, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id_val = create_result.data["guild_id"]
        service.add_member(AddGuildMemberCommand(guild_id=guild_id_val, inviter_player_id=1, new_member_player_id=2))
        command = DisbandGuildCommand(guild_id=guild_id_val, player_id=2)
        with pytest.raises(GuildCommandException):
            service.disband_guild(command)

    # --- leave_guild leader succession (Phase 5) ---
    def test_leave_guild_leader_assigns_successor_by_joined_at(self, setup_service):
        """リーダー脱退時、joined_at が最も古いオフィサー（いなければメンバー）が後継リーダーになること"""
        service, guild_repo, _, _ = setup_service
        create_result = service.create_guild(
            CreateGuildCommand(spot_id=TEST_SPOT_ID, location_area_id=TEST_LOCATION_AREA_ID, name="G", description="", creator_player_id=1)
        )
        guild_id_val = create_result.data["guild_id"]
        service.add_member(AddGuildMemberCommand(guild_id=guild_id_val, inviter_player_id=1, new_member_player_id=2))
        service.add_member(AddGuildMemberCommand(guild_id=guild_id_val, inviter_player_id=1, new_member_player_id=3))
        service.change_role(ChangeGuildRoleCommand(guild_id=guild_id_val, changer_player_id=1, target_player_id=2, new_role="officer"))
        leave_cmd = LeaveGuildCommand(guild_id=guild_id_val, player_id=1)
        result = service.leave_guild(leave_cmd)
        assert result.success is True
        guild = guild_repo.find_by_id(GuildId(guild_id_val))
        assert guild.is_member(PlayerId(2)) is True
        assert guild.is_member(PlayerId(3)) is True
        assert guild.get_member(PlayerId(2)).role == GuildRole.LEADER
        assert guild.get_member(PlayerId(3)).role == GuildRole.MEMBER
