from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people import NameInText, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import NotSeenInDim, NotSeenWithoutActor, SightTarget, SightTexts
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class NoticedOnWaking:
    text: TextWithUnassignedPeople

    def placeholders(self) -> frozenset[str]:
        return self.text.placeholders()

    def target_of(
        self, person: PersonId, people: Mapping[str, PersonId], names: Mapping[str, NameInText]
    ) -> SightTarget:
        noticed = self.text.about_named(people, names)
        # 倒れている相手は起きてから気づく文だけを受け取るので、ほかの欄にも同じ文を置く。
        return SightTarget(
            person=person,
            texts=SightTexts(
                clear=noticed, dim=NotSeenInDim(), unseen_actor=NotSeenWithoutActor(), noticed_later=noticed
            ),
        )
