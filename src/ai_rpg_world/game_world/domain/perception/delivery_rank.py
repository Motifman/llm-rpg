from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import final

from ai_rpg_world.game_world.domain.perception.salience import Salience


class Sense(IntEnum):
    OWN_BODY = 0
    SIGHT = 1
    SOUND = 2
    ANNOUNCEMENT = 3


@final
@dataclass(frozen=True, order=True)
class DeliveryRank:
    sense: Sense
    stands_back: bool

    @classmethod
    def of(cls, sense: Sense, salience: Salience) -> DeliveryRank:
        return cls(sense=sense, stands_back=not salience.stands_out())
