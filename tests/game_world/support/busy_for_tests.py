from __future__ import annotations

from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import Busy
from ai_rpg_world.game_world.domain.value_object import WorldTick


def busy_until(until: WorldTick) -> Busy:
    return Busy(until=until, doing=TextAboutPeople(TextWithUnassignedPeople("何かをしている"), {}))
