from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.unavailable_object_operation import UnavailableObjectOperation
from ai_rpg_world.game_world.domain.people import TextAboutPeople

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class Doable:
    pass


@final
@dataclass(frozen=True)
class NotNow:
    reason: TextAboutPeople
    about_object_state: bool = False


@final
@dataclass(frozen=True)
class AvailableAction:
    attempt: ActionAttempt
    standing: Doable | NotNow


@final
@dataclass(frozen=True)
class AvailableActions:
    actions: tuple[AvailableAction, ...]

    def unavailable_on_objects(self, design: WorldDesign) -> tuple[UnavailableObjectOperation, ...]:
        return tuple(
            operation
            for action in self.actions
            if isinstance(action.standing, NotNow) and action.standing.about_object_state
            for operation in action.attempt.unavailable_on_object(design, action.standing.reason)
        )

    def offered_as_choices(self, design: WorldDesign) -> AvailableActions:
        # 物のいまできない操作は場面の物の行の下に出すので、行動の候補には重ねて出さない (古い run と同じ)
        return AvailableActions(
            tuple(
                action
                for action in self.actions
                if not (
                    isinstance(action.standing, NotNow)
                    and action.standing.about_object_state
                    and action.attempt.unavailable_on_object(design, action.standing.reason)
                )
            )
        )
