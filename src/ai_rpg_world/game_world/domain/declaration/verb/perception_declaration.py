from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_declaration import NoAnnouncement
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
@dataclass(frozen=True, kw_only=True)
class PerceptionDeclaration:
    witness: SightTextsDeclaration
    target: SightTextsDeclaration | NoTarget
    sound: SoundDeclaration | Silent
    seen_in_dark: bool
    announcement: NoAnnouncement
    on_failure: SightTextsDeclaration | NoFailureWitness = field(default_factory=NoFailureWitness)
    salience: Salience
