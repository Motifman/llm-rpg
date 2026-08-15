"""手番入口で一度決めた主体 (PlayerId + BeingId の対)。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class ActingBeing:
    player_id: PlayerId
    being_id: BeingId
