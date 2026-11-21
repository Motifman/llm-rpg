from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.pass_world_time import PassWorldTime, PassWorldTimeCommand
from ai_rpg_world.game_world.application.settle_world_conditions import (
    SettleWorldConditions,
    SettleWorldConditionsCommand,
)
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.settling_occasion import SettlingOccasion
from ai_rpg_world.game_world.domain.exception.world_progress_exception import WorldAlreadyEndedException


@final
@dataclass(frozen=True)
class AcceptWorldTimePassageCommand:
    pass


@final
@dataclass(frozen=True)
class WorldTimePassed:
    pass


@final
@dataclass(frozen=True)
class WorldTimePassageRefused:
    code: RefusalCode


WorldTimePassageReply = WorldTimePassed | WorldTimePassageRefused


@final
class AcceptWorldTimePassage:
    def __init__(self, scope: CommandScope, pass_time: PassWorldTime, settle: SettleWorldConditions) -> None:
        self._scope = scope
        self._pass_time = pass_time
        self._settle = settle

    def __call__(self, command: AcceptWorldTimePassageCommand) -> WorldTimePassageReply:
        try:
            self._scope.run(lambda session: session.ending().admit_change())
        except WorldAlreadyEndedException as ended:
            return WorldTimePassageRefused(RefusalCode.of(ended))
        self._pass_time(PassWorldTimeCommand())
        self._settle(SettleWorldConditionsCommand(SettlingOccasion.AFTER_WORLD_TIME_PASSED))
        return WorldTimePassed()
