from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people import NameInText, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import NotNoticedLater, Salience, SoundSource, SoundStimulus
from ai_rpg_world.game_world.domain.sound.loudness import Loudness
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick


@final
@dataclass(frozen=True)
class SoundDeclaration:
    loudness: Loudness
    clear: TextWithUnassignedPeople
    muffled: TextWithUnassignedPeople

    def placeholders(self) -> frozenset[str]:
        return self.clear.placeholders() | self.muffled.placeholders()

    def heard_at(
        self,
        origin: SpotId,
        people: Mapping[str, PersonId],
        names: Mapping[str, NameInText],
        source: SoundSource,
        salience: Salience,
        at: WorldTick,
    ) -> SoundStimulus:
        return SoundStimulus(
            origin=origin,
            loudness=self.loudness,
            clear=self.clear.about_named(people, names),
            muffled=self.muffled.about_named(people, names),
            noticed_later=NotNoticedLater(),
            source=source,
            involved=tuple(dict.fromkeys(people.values())),
            salience=salience,
            at=at,
        )
