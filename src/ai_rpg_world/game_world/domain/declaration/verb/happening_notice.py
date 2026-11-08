from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sight_texts_declaration import SightTextsDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import Salience


@final
@dataclass(frozen=True)
class SightAt:
    spot: SpotDeclaration
    texts: SightTextsDeclaration
    salience: Salience


@final
@dataclass(frozen=True)
class SoundFrom:
    spot: SpotDeclaration
    sound: SoundDeclaration
    salience: Salience


@final
@dataclass(frozen=True)
class AnnouncementTo:
    audience: PeopleSelection
    text: TextWithUnassignedPeople
    salience: Salience


@final
@dataclass(frozen=True)
class NoNotice:
    pass


HappeningNotice = SightAt | SoundFrom | AnnouncementTo
