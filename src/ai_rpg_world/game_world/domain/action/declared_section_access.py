from __future__ import annotations

from typing import Protocol

from ai_rpg_world.game_world.domain.action.action_attempt import Exertion
from ai_rpg_world.game_world.domain.declaration.spot import SpotSectionDeclaration


class DeclaredSectionAccess(Protocol):
    @property
    def section(self) -> SpotSectionDeclaration: ...

    @property
    def exertion(self) -> Exertion: ...
