from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception.bodily_stimulus import BodilyStimulus
from ai_rpg_world.game_world.domain.perception.no_target import NoTarget
from ai_rpg_world.game_world.domain.perception.not_noticed_later import NotNoticedLater
from ai_rpg_world.game_world.domain.perception.not_seen_in_dim import NotSeenInDim
from ai_rpg_world.game_world.domain.perception.not_seen_without_actor import NotSeenWithoutActor
from ai_rpg_world.game_world.domain.perception.salience import Background, Notable
from ai_rpg_world.game_world.domain.perception.sight_stimulus import SightStimulus, SightTexts
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick


@final
@dataclass(frozen=True)
class ItemRanOutNotice:
    text: TextAboutPeople
    at: WorldTick

    def when_carried(self, person: PersonId) -> BodilyStimulus | SightStimulus:
        # 持っていた本人には、灯が消えるなど身の回りが変わることなので、考え直す目安にする。
        return BodilyStimulus(person=person, text=self.text, salience=Notable(), at=self.at)

    def when_lying(self, spot: SpotId) -> BodilyStimulus | SightStimulus:
        return SightStimulus(
            where=spot,
            witness=SightTexts(
                clear=self.text, dim=NotSeenInDim(), unseen_actor=NotSeenWithoutActor(), noticed_later=NotNoticedLater()
            ),
            target=NoTarget(),
            seen_in_dark=False,
            manner=Openly(),
            actor_departed=False,
            involved=(),
            salience=Background(),
            always_delivered=False,
            at=self.at,
        )
