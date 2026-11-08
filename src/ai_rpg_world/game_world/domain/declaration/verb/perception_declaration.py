from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import AnnouncementTo
from ai_rpg_world.game_world.domain.declaration.verb.sight_texts_declaration import SightTextsDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.sound_declaration import SoundDeclaration
from ai_rpg_world.game_world.domain.perception import NoTarget, Salience


@final
@dataclass(frozen=True)
class Silent:
    pass


@final
@dataclass(frozen=True)
class NoFailureWitness:
    pass


@final
@dataclass(frozen=True)
class PerceptionDeclaration:
    witness: SightTextsDeclaration
    target: SightTextsDeclaration | NoTarget
    sound: SoundDeclaration | Silent
    seen_in_dark: bool
    announcement: AnnouncementTo | NoAnnouncement
    on_failure: SightTextsDeclaration | NoFailureWitness
    salience: Salience
