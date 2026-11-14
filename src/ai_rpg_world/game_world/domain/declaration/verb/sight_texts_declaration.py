from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar, final

from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import NotNoticedLater, NotSeenInDim, NotSeenWithoutActor, SightTexts
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId

_NotWritten = TypeVar("_NotWritten", NotSeenInDim, NotSeenWithoutActor, NotNoticedLater)


@final
@dataclass(frozen=True)
class SightTextsDeclaration:
    clear: TextWithUnassignedPeople
    dim: TextWithUnassignedPeople | NotSeenInDim
    unseen_actor: TextWithUnassignedPeople | NotSeenWithoutActor
    noticed_later: TextWithUnassignedPeople | NotNoticedLater

    def placeholders(self) -> frozenset[str]:
        texts = (self.clear, self.dim, self.unseen_actor, self.noticed_later)
        return frozenset().union(*(text.placeholders() for text in texts if isinstance(text, TextWithUnassignedPeople)))

    def about_named(self, people: Mapping[str, PersonId], names: Mapping[str, DisplayName]) -> SightTexts:
        return SightTexts(
            clear=self.clear.about_named(people, names),
            dim=_about_named(self.dim, people, names),
            unseen_actor=_about_named(self.unseen_actor, people, names),
            noticed_later=_about_named(self.noticed_later, people, names),
        )


def _about_named(
    text: TextWithUnassignedPeople | _NotWritten, people: Mapping[str, PersonId], names: Mapping[str, DisplayName]
) -> TextAboutPeople | _NotWritten:
    if isinstance(text, TextWithUnassignedPeople):
        return text.about_named(people, names)
    return text
