from __future__ import annotations

from typing import Protocol

from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration


class DeclaredGroupDecisionRules(Protocol):
    @property
    def decision(self) -> GroupDecisionDeclaration: ...

    @property
    def voters(self) -> PeopleSelection: ...

    @property
    def choices(self) -> PeopleSelection: ...
