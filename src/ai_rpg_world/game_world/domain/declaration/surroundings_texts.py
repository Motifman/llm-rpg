from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import final

from ai_rpg_world.game_world.domain.exception.surroundings_texts_exception import (
    BlankPeopleJoinerException,
    NoPeopleToListException,
    PeopleNotWrittenOnceException,
    PersonInSurroundingsNoticeException,
)
from ai_rpg_world.game_world.domain.people import PersonRef, TextWithUnassignedPeople, Unidentified
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.value_object import DisplayName

_PEOPLE = "people"


@final
@dataclass(frozen=True)
class SceneTexts:
    heading: DisplayName
    objects: DisplayName
    destinations: DisplayName
    ground_items: DisplayName
    count_mark: DisplayName
    pitch_dark: DisplayName


@final
@dataclass(frozen=True)
class SurroundingsTexts:
    people_here: TextWithUnassignedPeople
    bodies_here: TextWithUnassignedPeople
    joiner: str
    waking: TextWithUnassignedPeople
    darkening: TextWithUnassignedPeople
    scene: SceneTexts

    def __post_init__(self) -> None:
        for name, text in (("people_here", self.people_here), ("bodies_here", self.bodies_here)):
            if _holes_in(text) != [_PEOPLE]:
                raise PeopleNotWrittenOnceException(
                    f"SurroundingsTexts.{name} must write {{{_PEOPLE}}} exactly once and nothing else,"
                    f" got {text.template!r}"
                )
        for name, text in (("waking", self.waking), ("darkening", self.darkening)):
            if text.placeholders():
                raise PersonInSurroundingsNoticeException(
                    f"SurroundingsTexts.{name} cannot name people, got {text.template!r}"
                )
        if not isinstance(self.joiner, str) or not self.joiner.strip() or self.joiner.splitlines() != [self.joiner]:
            raise BlankPeopleJoinerException(
                f"SurroundingsTexts.joiner must be a non-blank single line, got {self.joiner!r}"
            )

    def scene_as_seen(
        self, *, people: tuple[PersonRef | Unidentified, ...], bodies: tuple[PersonRef | Unidentified, ...]
    ) -> TextWithAssignedPeople:
        if not people and not bodies:
            raise NoPeopleToListException("there is no one to list in the surroundings")
        holes: dict[str, PersonRef | Unidentified] = {}
        parts = [
            self._listing(text, group, holes)
            for text, group in ((self.people_here, people), (self.bodies_here, bodies))
            if group
        ]
        return TextWithUnassignedPeople("".join(parts)).assign(holes)

    def _listing(
        self,
        text: TextWithUnassignedPeople,
        group: tuple[PersonRef | Unidentified, ...],
        holes: dict[str, PersonRef | Unidentified],
    ) -> str:
        # 1 つの穴には 1 人しか入らず、名前は見る人の側で埋まる。つなぐのは名前ではなく穴どうしになる。
        keys = []
        for person in group:
            key = f"person_{len(holes) + 1}"
            holes[key] = person
            keys.append(key)
        listed = TextWithUnassignedPeople.literal(self.joiner).template.join(f"{{{key}}}" for key in keys)
        rebuilt: list[str] = []
        for literal, field_name, _, _ in Formatter().parse(text.template):
            rebuilt.append(TextWithUnassignedPeople.literal(literal).template)
            if field_name is not None:
                rebuilt.append(listed)
        return "".join(rebuilt)


def _holes_in(text: TextWithUnassignedPeople) -> list[str]:
    return [field_name for _, field_name, _, _ in Formatter().parse(text.template) if field_name is not None]
