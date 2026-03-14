"""LLM 向けのスキル使用 facade。"""

from typing import Optional

from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.skill.contracts.commands import (
    AcceptSkillProposalCommand,
    ActivatePlayerAwakenedModeCommand,
    EquipPlayerSkillCommand,
    RejectSkillProposalCommand,
    UsePlayerSkillCommand,
)
from ai_rpg_world.application.skill.exceptions.command.skill_command_exception import (
    SkillCommandException,
)
from ai_rpg_world.application.skill.services.awakened_mode_defaults import (
    DEFAULT_AWAKENED_MODE_ACTIVATION,
)
from ai_rpg_world.application.skill.services.skill_command_service import SkillCommandService
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier


class PlayerSkillToolApplicationService:
    """LLM から使いやすいスキル使用 API。"""

    def __init__(
        self,
        skill_command_service: SkillCommandService,
        player_status_repository: PlayerStatusRepository,
        time_provider: GameTimeProvider,
    ) -> None:
        self._skill_command_service = skill_command_service
        self._player_status_repository = player_status_repository
        self._time_provider = time_provider

    def use_skill(
        self,
        *,
        player_id: int,
        skill_loadout_id: int,
        skill_slot_index: int,
        target_direction: Optional[str] = None,
        auto_aim: bool = False,
    ) -> None:
        status = self._player_status_repository.find_by_id(PlayerId.create(player_id))
        if status is None or status.current_spot_id is None:
            raise SkillCommandException(f"player status not found: {player_id}")
        self._skill_command_service.use_player_skill(
            UsePlayerSkillCommand(
                player_id=player_id,
                loadout_id=skill_loadout_id,
                slot_index=skill_slot_index,
                current_tick=self._time_provider.get_current_tick().value,
                spot_id=str(int(status.current_spot_id)),
                target_direction=target_direction,
                auto_aim=auto_aim,
            )
        )

    def equip_skill(
        self,
        *,
        player_id: int,
        loadout_id: int,
        deck_tier: DeckTier,
        slot_index: int,
        skill_id: int,
    ) -> None:
        self._skill_command_service.equip_player_skill(
            EquipPlayerSkillCommand(
                player_id=player_id,
                loadout_id=loadout_id,
                deck_tier=deck_tier,
                slot_index=slot_index,
                skill_id=skill_id,
            )
        )

    def accept_skill_proposal(
        self,
        *,
        progress_id: int,
        proposal_id: int,
    ) -> None:
        self._skill_command_service.accept_skill_proposal(
            AcceptSkillProposalCommand(
                progress_id=progress_id,
                proposal_id=proposal_id,
            )
        )

    def reject_skill_proposal(
        self,
        *,
        progress_id: int,
        proposal_id: int,
    ) -> None:
        self._skill_command_service.reject_skill_proposal(
            RejectSkillProposalCommand(
                progress_id=progress_id,
                proposal_id=proposal_id,
            )
        )

    def activate_awakened_mode(
        self,
        *,
        player_id: int,
        loadout_id: int,
    ) -> None:
        self._skill_command_service.activate_player_awakened_mode(
            ActivatePlayerAwakenedModeCommand(
                player_id=player_id,
                loadout_id=loadout_id,
                current_tick=self._time_provider.get_current_tick().value,
                duration_ticks=DEFAULT_AWAKENED_MODE_ACTIVATION.duration_ticks,
                cooldown_reduction_rate=DEFAULT_AWAKENED_MODE_ACTIVATION.cooldown_reduction_rate,
                mp_cost=DEFAULT_AWAKENED_MODE_ACTIVATION.mp_cost,
                stamina_cost=DEFAULT_AWAKENED_MODE_ACTIVATION.stamina_cost,
                hp_cost=DEFAULT_AWAKENED_MODE_ACTIVATION.hp_cost,
            )
        )
