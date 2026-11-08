from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import NotNoticedLater, NotSeenInDim, NotSeenWithoutActor


@final
@dataclass(frozen=True)
class SightTextsDeclaration:
    clear: TextWithUnassignedPeople
    dim: TextWithUnassignedPeople | NotSeenInDim = field(default_factory=NotSeenInDim)
    unseen_actor: TextWithUnassignedPeople | NotSeenWithoutActor = field(default_factory=NotSeenWithoutActor)
    noticed_later: TextWithUnassignedPeople | NotNoticedLater = field(default_factory=NotNoticedLater)
