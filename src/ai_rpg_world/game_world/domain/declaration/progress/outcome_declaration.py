from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import DisplayName, OutcomeId, PersonId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.perception.announcement_stimulus import AnnouncementStimulus


@final
@dataclass(frozen=True)
class OutcomeDeclaration:
    outcome_id: OutcomeId
    name: DisplayName
    announcement: TextWithUnassignedPeople

    def announcement_to(self, person: PersonId, at: WorldTick) -> AnnouncementStimulus:
        # perception をモジュールの頭で import すると、action の読み込みと循環する。
        from ai_rpg_world.game_world.domain.perception.announcement_stimulus import AnnouncementStimulus
        from ai_rpg_world.game_world.domain.perception.salience import Notable

        return AnnouncementStimulus(
            audience=frozenset({person}),
            text=self.announcement.about({"each_person": person}),
            salience=Notable(),
            at=at,
            reaches_who_left_the_world=True,
        )
