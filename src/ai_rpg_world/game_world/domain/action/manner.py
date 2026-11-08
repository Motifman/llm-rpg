from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.declared_interaction import DeclaredInteraction
from ai_rpg_world.game_world.domain.exception.action_exception import StealthNotAllowedException


@final
@dataclass(frozen=True)
class Openly:
    def require_allowed_by(self, interaction: DeclaredInteraction) -> None:
        pass

    def noticed_when(self, notices: Callable[[], bool]) -> bool:
        return True


@final
@dataclass(frozen=True)
class Stealthily:
    def require_allowed_by(self, interaction: DeclaredInteraction) -> None:
        if not interaction.allows_stealth:
            raise StealthNotAllowedException(f"{interaction.interaction_id.value} cannot be done stealthily")

    def noticed_when(self, notices: Callable[[], bool]) -> bool:
        return notices()


Manner = Openly | Stealthily
