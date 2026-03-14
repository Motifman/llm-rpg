from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.skill.exceptions.command.skill_command_exception import (
    SkillCommandException,
)
from ai_rpg_world.application.skill.services.player_skill_tool_service import (
    PlayerSkillToolApplicationService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier
from ai_rpg_world.domain.common.value_object import WorldTick


@pytest.fixture
def skill_command_service():
    return MagicMock()


@pytest.fixture
def player_status_repository():
    return MagicMock()


@pytest.fixture
def time_provider():
    provider = MagicMock()
    provider.get_current_tick.return_value = WorldTick(123)
    return provider


@pytest.fixture
def service(skill_command_service, player_status_repository, time_provider):
    return PlayerSkillToolApplicationService(
        skill_command_service=skill_command_service,
        player_status_repository=player_status_repository,
        time_provider=time_provider,
    )


class TestPlayerSkillToolApplicationService:
    def test_use_skill_builds_command_with_current_spot(
        self,
        service,
        skill_command_service,
        player_status_repository,
    ):
        status = MagicMock()
        status.current_spot_id = 7
        player_status_repository.find_by_id.return_value = status

        service.use_skill(
            player_id=1,
            skill_loadout_id=10,
            skill_slot_index=2,
            target_direction="NORTH",
            auto_aim=True,
        )

        player_status_repository.find_by_id.assert_called_once_with(PlayerId.create(1))
        command = skill_command_service.use_player_skill.call_args.args[0]
        assert command.player_id == 1
        assert command.loadout_id == 10
        assert command.slot_index == 2
        assert command.current_tick == 123
        assert command.spot_id == "7"
        assert command.target_direction == "NORTH"
        assert command.auto_aim is True

    def test_use_skill_raises_when_player_status_missing(
        self,
        service,
        player_status_repository,
    ):
        player_status_repository.find_by_id.return_value = None

        with pytest.raises(SkillCommandException, match="player status not found: 1"):
            service.use_skill(
                player_id=1,
                skill_loadout_id=10,
                skill_slot_index=2,
            )

    def test_equip_skill_delegates_to_command_service(
        self,
        service,
        skill_command_service,
    ):
        service.equip_skill(
            player_id=1,
            loadout_id=10,
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=1001,
        )

        command = skill_command_service.equip_player_skill.call_args.args[0]
        assert command.player_id == 1
        assert command.loadout_id == 10
        assert command.deck_tier == DeckTier.NORMAL
        assert command.slot_index == 0
        assert command.skill_id == 1001

    def test_accept_skill_proposal_delegates_to_command_service(
        self,
        service,
        skill_command_service,
    ):
        service.accept_skill_proposal(progress_id=20, proposal_id=3)

        command = skill_command_service.accept_skill_proposal.call_args.args[0]
        assert command.progress_id == 20
        assert command.proposal_id == 3

    def test_reject_skill_proposal_delegates_to_command_service(
        self,
        service,
        skill_command_service,
    ):
        service.reject_skill_proposal(progress_id=20, proposal_id=4)

        command = skill_command_service.reject_skill_proposal.call_args.args[0]
        assert command.progress_id == 20
        assert command.proposal_id == 4

    def test_activate_awakened_mode_delegates_with_server_side_defaults(
        self,
        service,
        skill_command_service,
    ):
        service.activate_awakened_mode(player_id=1, loadout_id=10)

        command = skill_command_service.activate_player_awakened_mode.call_args.args[0]
        assert command.player_id == 1
        assert command.loadout_id == 10
        assert command.current_tick == 123
        assert command.duration_ticks == 50
        assert command.cooldown_reduction_rate == 0.5
        assert command.mp_cost == 20
        assert command.stamina_cost == 30
        assert command.hp_cost == 0
