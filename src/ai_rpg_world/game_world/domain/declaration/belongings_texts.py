from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.surroundings_texts_exception import UnfillableSceneTextException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception.announcement_stimulus import AnnouncementStimulus
from ai_rpg_world.game_world.domain.perception.salience import Background
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId, WorldTick


@final
@dataclass(frozen=True)
class BelongingsTexts:
    received: TextWithUnassignedPeople
    given_up: TextWithUnassignedPeople

    def __post_init__(self) -> None:
        # 品物の名前を書き忘れると、何が増えたか減ったかが静かに消えるので、読み込みで断る
        for name, text in (("received", self.received), ("given_up", self.given_up)):
            if text.placeholders() != {"item"}:
                raise UnfillableSceneTextException(
                    f"BelongingsTexts.{name} must write {{item}} and nothing else, got {text.template!r}"
                )

    def received_by(self, person: PersonId, item: DisplayName, at: WorldTick) -> AnnouncementStimulus:
        return _told(person, self.received, item, at)

    def given_up_by(
        self, person: PersonId, item: DisplayName, at: WorldTick, *, ran_out: bool
    ) -> tuple[AnnouncementStimulus, ...]:
        # 使い切って消えた品物は、尽きたことを品物の知らせ (燃え尽きた、など) で伝える。捨てていないのに「捨てた」と読めるのを避ける
        if ran_out:
            return ()
        return (_told(person, self.given_up, item, at),)


def _told(person: PersonId, text: TextWithUnassignedPeople, item: DisplayName, at: WorldTick) -> AnnouncementStimulus:
    # 持ち物の出入りは本人にしか分からない。見聞きしたことの言い換えではないので、1 人に 1 つの数に入れない知らせにする
    return AnnouncementStimulus(
        audience=frozenset({person}),
        text=text.with_names({"item": item}).about({}),
        salience=Background(),
        at=at,
    )
