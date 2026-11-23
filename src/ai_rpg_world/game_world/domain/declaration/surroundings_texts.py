from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import final

from ai_rpg_world.game_world.domain.declaration.body_tiers import HitPointsTiers, NeedTiers
from ai_rpg_world.game_world.domain.exception.surroundings_texts_exception import (
    BlankPeopleJoinerException,
    NoPeopleToListException,
    PeopleNotWrittenOnceException,
    PersonInSurroundingsNoticeException,
    UnfillableSceneTextException,
)
from ai_rpg_world.game_world.domain.people import PersonRef, TextWithUnassignedPeople, Unidentified
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.value_object import DisplayName

_PEOPLE = "people"


SCENE_LINE_NAMES = {
    "description": ("description",),
    "atmosphere": ("parts",),
    "lighting": ("lighting",),
    "sound": ("sound",),
    "temperature": ("temperature",),
    "smell": ("smell",),
    "atmosphere_joiner": (),
    "weather": ("weather",),
    "clock": ("time",),
    "day_phase": ("phase",),
    "dark_day_phase": ("phase",),
    "destinations": (),
    "destination": ("passage", "spot", "status"),
    "passable": (),
    "impassable": ("state",),
    "objects": (),
    "object": ("object", "look", "description"),
    "object_without_look": ("object", "description"),
    "no_objects": (),
    "no_objects_in_dark": (),
    "objects_in_dark": (),
    "people": (),
    "no_people": (),
    "person": ("person", "condition", "carried"),
    "person_looks": ("looks",),
    "person_down": (),
    "person_dead": (),
    "carried": ("items",),
    "carrying_nothing": (),
    "carried_joiner": (),
    "belongings": (),
    "belonging": ("item", "count", "description", "held"),
    "belonging_count": ("count",),
    "belonging_description": ("description",),
    "belonging_held": (),
    "body": (),
    "hit_points": ("tier", "current", "maximum", "change"),
    "hunger": ("tier", "amount", "limit", "change"),
    "fatigue": ("tier", "amount", "limit", "change"),
    "body_change": ("change",),
    "fatigue_felt": ("feel",),
}


@final
@dataclass(frozen=True)
class SceneTexts:
    heading: DisplayName
    description: str
    atmosphere: str
    lighting: str
    sound: str
    temperature: str
    smell: str
    atmosphere_joiner: str
    weather: str
    clock: str
    day_phase: str
    dark_day_phase: str
    destinations: str
    destination: str
    passable: str
    impassable: str
    objects: str
    object: str
    object_without_look: str
    no_objects: str
    no_objects_in_dark: str
    objects_in_dark: str
    people: str
    no_people: str
    person: str
    person_looks: str
    person_down: str
    person_dead: str
    carried: str
    carrying_nothing: str
    carried_joiner: str
    belongings: str
    belonging: str
    belonging_count: str
    belonging_description: str
    belonging_held: str
    body: str
    hit_points: str
    hunger: str
    fatigue: str
    fatigue_felt: str
    body_change: str
    need_tiers: NeedTiers
    hit_points_tiers: HitPointsTiers
    ground_items: DisplayName
    count_mark: DisplayName
    pitch_dark: DisplayName

    def __post_init__(self) -> None:
        # 書けない言い回しと、埋めるべき値を書き忘れた言い回しを、場面を書くときではなく、読み込みのときに断る
        for field_name, names in SCENE_LINE_NAMES.items():
            text = getattr(self, field_name)
            try:
                written = {name for _, name, _, _ in Formatter().parse(text) if name is not None}
                if written != set(names):
                    raise UnfillableSceneTextException(
                        f"SceneTexts.{field_name} must write exactly {sorted(names)}, got {text!r}"
                    )
                text.format(**dict.fromkeys(names, ""))
            except ValueError as error:
                raise UnfillableSceneTextException(f"SceneTexts.{field_name} cannot be read: {text!r}") from error


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
