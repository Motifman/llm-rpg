from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.effect.effect import Effect


@final
@dataclass(frozen=True)
class GroupDecisionRulesDeclaration:
    decision: GroupDecisionDeclaration
    voters: PeopleSelection
    choices: PeopleSelection
    when_decided: Effect
    when_undecided: Effect
