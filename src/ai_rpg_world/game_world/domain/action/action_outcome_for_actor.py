from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.people import TextAboutPeople

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
    from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class UnsummarizedAction:
    pass


@final
@dataclass(frozen=True)
class ActionOutcomeForActor:
    result: TextAboutPeople
    summary: TextAboutPeople | UnsummarizedAction

    @classmethod
    def of_done(cls, attempt: ActionAttempt, design: WorldDesign, situation: ActorSituation) -> ActionOutcomeForActor:
        return cls(result=attempt.done_text_in(design, situation), summary=attempt.summary_in(design, situation))
