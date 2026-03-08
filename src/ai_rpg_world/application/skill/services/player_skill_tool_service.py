"""LLM 向けのスキル使用 facade。"""

from typing import Optional

from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.skill.contracts.commands import UsePlayerSkillCommand
from ai_rpg_world.application.skill.exceptions.command.skill_command_exception import (
    SkillCommandException,
)
from ai_rpg_world.application.skill.services.skill_command_service import SkillCommandService
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


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
