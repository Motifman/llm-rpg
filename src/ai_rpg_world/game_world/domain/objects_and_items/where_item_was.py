from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception import (
    Background,
    BodilyStimulus,
    Notable,
    NoTarget,
    NotNoticedLater,
    NotSeenInDim,
    NotSeenWithoutActor,
    SightStimulus,
    SightTexts,
)
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick


@final
@dataclass(frozen=True)
class CarriedBy:
    person: PersonId

    def ran_out_stimulus(self, text: TextAboutPeople, at: WorldTick) -> BodilyStimulus:
        # 持っていた本人には、灯が消えるなど身の回りが変わることなので、考え直す目安にする。
        return BodilyStimulus(person=self.person, text=text, salience=Notable(), at=at)


@final
@dataclass(frozen=True)
class LyingAt:
    spot: SpotId

    def ran_out_stimulus(self, text: TextAboutPeople, at: WorldTick) -> SightStimulus:
        return SightStimulus(
            where=self.spot,
            witness=SightTexts(
                clear=text, dim=NotSeenInDim(), unseen_actor=NotSeenWithoutActor(), noticed_later=NotNoticedLater()
            ),
            target=NoTarget(),
            seen_in_dark=False,
            manner=Openly(),
            actor_departed=False,
            involved=(),
            salience=Background(),
            always_delivered=False,
            at=at,
        )


WhereItemWas = CarriedBy | LyingAt
