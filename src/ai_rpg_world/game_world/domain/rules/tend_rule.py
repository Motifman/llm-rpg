from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai_rpg_world.game_world.domain.exception.rules_exception import TendingNotDeclaredException
from ai_rpg_world.game_world.domain.value_object import Rate, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.person import PersonVitals


@dataclass(frozen=True)
class TendRule:
    revive_hp_rate: Rate

    def allows_tending(self) -> bool:
        return True

    def revive(self, vitals: PersonVitals, now: WorldTick) -> None:
        vitals.revive(self.revive_hp_rate, now)


@dataclass(frozen=True)
class NoTending:
    def allows_tending(self) -> bool:
        return False

    def revive(self, vitals: PersonVitals, now: WorldTick) -> None:
        raise TendingNotDeclaredException(f"this world declares no tending, yet {vitals.person.value} was tended")
