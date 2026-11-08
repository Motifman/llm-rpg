from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import NotNoticedLater, NotSeenInDim, NotSeenWithoutActor


@final
@dataclass(frozen=True)
class SightTextsDeclaration:
    clear: TextWithUnassignedPeople
    dim: TextWithUnassignedPeople | NotSeenInDim
    unseen_actor: TextWithUnassignedPeople | NotSeenWithoutActor
    noticed_later: TextWithUnassignedPeople | NotNoticedLater
