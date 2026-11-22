from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, final

from ai_rpg_world.being.contract import Here, Scene
from ai_rpg_world.game_world.domain.declaration.object_and_item.object_declaration import ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.object_looks_declaration import NoLook
from ai_rpg_world.game_world.domain.exception.surroundings_exception import (
    HeldItemNotCarriedException,
    ThingFromAnotherSpotException,
    UnrevealedThingNotDeclaredHiddenException,
)
from ai_rpg_world.game_world.domain.lighting import Lighting, SeesClearly, SeesNothing, SeesShapes, SightQuality
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import PersonRef, TextWithUnassignedPeople, Unidentified
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived
from ai_rpg_world.game_world.domain.perception.scene_conditions import SceneConditions
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    PersonId,
    SpotId,
    SpotSectionId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts.location import OpenArea
from ai_rpg_world.game_world.domain.whereabouts.passage_in_state import PassageInState

if TYPE_CHECKING:
    # 実行時に import すると循環する。
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SceneTexts, SurroundingsTexts
    from ai_rpg_world.game_world.domain.declaration.time_and_weather.clock_wording import ClockWording
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
    from ai_rpg_world.game_world.domain.declaration.world_words import WorldWords
    from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen


@final
@dataclass(frozen=True)
class _SightRule:
    shows_description: bool
    shows_people: bool
    identifies_people: bool
    shows_items: bool
    shows_objects_unseen_in_dark: bool


_RULES: Mapping[SightQuality, _SightRule] = MappingProxyType(
    {
        SeesClearly(): _SightRule(
            shows_description=True,
            shows_people=True,
            identifies_people=True,
            shows_items=True,
            shows_objects_unseen_in_dark=True,
        ),
        SeesShapes(): _SightRule(
            shows_description=True,
            shows_people=True,
            identifies_people=False,
            shows_items=False,
            shows_objects_unseen_in_dark=False,
        ),
        SeesNothing(): _SightRule(
            shows_description=False,
            shows_people=False,
            identifies_people=False,
            shows_items=False,
            shows_objects_unseen_in_dark=False,
        ),
    }
)


@final
@dataclass(frozen=True)
class SeenPerson:
    person: PersonRef | Unidentified
    section: SpotSectionId | OpenArea
    visible_items: tuple[ItemInstanceId, ...]


@final
@dataclass(frozen=True)
class PresentPerson:
    person: PersonRef
    section: SpotSectionId | OpenArea
    held_items: tuple[ItemInstanceId, ...]
    all_items: tuple[ItemInstanceId, ...]

    def __post_init__(self) -> None:
        not_carried = set(self.held_items) - set(self.all_items)
        if not_carried:
            raise HeldItemNotCarriedException(
                f"person {self.person.handle.value} holds {sorted(i.value for i in not_carried)} without carrying them"
            )

    def seen_awake_with(self, sight: SightQuality) -> SeenPerson | None:
        return self._seen_with(_RULES[sight], self.held_items)

    def seen_down_with(self, sight: SightQuality) -> SeenPerson | None:
        return self._seen_with(_RULES[sight], self.all_items)

    def _seen_with(self, rule: _SightRule, items: tuple[ItemInstanceId, ...]) -> SeenPerson | None:
        if not rule.shows_people:
            return None
        return SeenPerson(
            person=self.person if rule.identifies_people else Unidentified(),
            section=self.section,
            visible_items=items if rule.shows_items else (),
        )


@final
@dataclass(frozen=True)
class SeenObject:
    declaration: ObjectDeclaration
    look: DescriptionText | NoLook


@final
@dataclass(frozen=True)
class ContainedObject:
    declaration: ObjectDeclaration
    revealed: bool
    look: DescriptionText | NoLook

    def __post_init__(self) -> None:
        if not self.revealed and not self.declaration.appearance.hidden_until_revealed:
            raise UnrevealedThingNotDeclaredHiddenException(
                f"object {self.declaration.object_id.value} is not declared hidden but is unrevealed"
            )

    def is_seen_with(self, sight: SightQuality) -> bool:
        return self.revealed and (
            self.declaration.appearance.seen_in_dark or _RULES[sight].shows_objects_unseen_in_dark
        )

    def seen(self) -> SeenObject:
        return SeenObject(declaration=self.declaration, look=self.look)


@final
@dataclass(frozen=True)
class ContainedPassage:
    passage: PassageInState
    revealed: bool

    def __post_init__(self) -> None:
        if not self.revealed and not self.passage.passage.hidden_until_revealed:
            raise UnrevealedThingNotDeclaredHiddenException(
                f"passage {self.passage.passage.passage_id.value} is not declared hidden but is unrevealed"
            )

    def is_seen(self) -> bool:
        return self.revealed


@final
@dataclass(frozen=True)
class SpotContents:
    spot: SpotDeclaration
    passages: tuple[ContainedPassage, ...]
    sections: tuple[SpotSectionDeclaration, ...]
    objects: tuple[ContainedObject, ...]
    ground_items: tuple[ItemInstanceId, ...]
    people: tuple[PresentPerson, ...]
    bodies: tuple[PresentPerson, ...]

    def __post_init__(self) -> None:
        here = self.spot.spot_id
        elsewhere = [
            *(f"object {o.declaration.object_id.value}" for o in self.objects if o.declaration.spot_id != here),
            *(f"section {s.section_id.value}" for s in self.sections if s.spot_id != here),
            *(
                f"passage {p.passage.passage.passage_id.value}"
                for p in self.passages
                if here not in p.passage.passage.ends
            ),
        ]
        if elsewhere:
            raise ThingFromAnotherSpotException(f"SpotContents of {here.value} contains {', '.join(elsewhere)}")

    @classmethod
    def around(
        cls, viewer: PersonId, spot: SpotDeclaration, facts: WorldFacts, design: WorldDesign, view: PeopleAsSeen
    ) -> SpotContents:
        people: list[PresentPerson] = []
        bodies: list[PresentPerson] = []
        for occupant, section in facts.whereabouts().sections_of_occupants_at(spot).items():
            if occupant.is_departed() or occupant.person == viewer:
                continue
            inventory = facts.inventory(occupant.person)
            present = PresentPerson(
                person=view.ref_of(occupant.person),
                section=section,
                held_items=inventory.held_items(),
                all_items=inventory.items(),
            )
            (people if facts.vitals(occupant.person).can_act() else bodies).append(present)
        passages = facts.passages()
        return cls(
            spot=spot,
            passages=tuple(
                ContainedPassage(passage=touching, revealed=passages.is_revealed(touching.passage))
                for touching in passages.touching(spot, facts.nouns().all_passages())
            ),
            sections=facts.nouns().sections_at(spot.spot_id),
            objects=tuple(
                ContainedObject(
                    declaration=declared,
                    revealed=facts.object_state(declared.object_id).is_revealed(),
                    look=design.looks_of(declared.object_id).look_now(facts),
                )
                for declared in facts.nouns().all_objects()
                if declared.spot_id == spot.spot_id
            ),
            ground_items=facts.ground_items(spot.spot_id).items(),
            people=tuple(people),
            bodies=tuple(bodies),
        )


class NamesInScene(Protocol):
    def spot_name(self, spot: SpotId) -> DisplayName: ...

    def item_name(self, item: ItemInstanceId) -> DisplayName: ...


class SurroundingsSenses(Protocol):
    def lighting_at(self, spot: SpotId) -> Lighting: ...

    def conditions_at(self, spot: SpotId) -> SceneConditions: ...

    def contents_at(self, spot: SpotId) -> SpotContents: ...


@final
@dataclass(frozen=True)
class VisibleSurroundings:
    spot: SpotDeclaration
    sight: SightQuality
    shows_description: bool
    passages: tuple[PassageInState, ...]
    sections: tuple[SpotSectionDeclaration, ...]
    objects: tuple[SeenObject, ...]
    ground_items: tuple[ItemInstanceId, ...]
    people: tuple[SeenPerson, ...]
    bodies: tuple[SeenPerson, ...]
    conditions: SceneConditions

    @classmethod
    def seen_by(cls, perceiver: Perceiver, senses: SurroundingsSenses) -> VisibleSurroundings | NothingInView:
        spot = perceiver.spot_in_view()
        if isinstance(spot, NothingInView):
            return spot
        return cls.seen_with(
            perceiver.sight_in(senses.lighting_at(spot)), senses.contents_at(spot), senses.conditions_at(spot)
        )

    @classmethod
    def seen_with(cls, sight: SightQuality, contents: SpotContents, conditions: SceneConditions) -> VisibleSurroundings:
        rule = _RULES[sight]
        return cls(
            spot=contents.spot,
            sight=sight,
            shows_description=rule.shows_description,
            passages=tuple(contained.passage for contained in contents.passages if contained.is_seen()),
            sections=contents.sections,
            objects=tuple(contained.seen() for contained in contents.objects if contained.is_seen_with(sight)),
            ground_items=contents.ground_items if rule.shows_items else (),
            people=_present(person.seen_awake_with(sight) for person in contents.people),
            bodies=_present(body.seen_down_with(sight) for body in contents.bodies),
            conditions=conditions,
        )

    def perceived_by(self, viewer: PersonId, texts: SurroundingsTexts, at: WorldTick) -> tuple[Perceived, ...]:
        if isinstance(self.sight, SeesNothing) or not (self.people or self.bodies):
            return ()
        return (
            Perceived(
                perceiver=viewer,
                text=texts.scene_as_seen(
                    people=tuple(seen.person for seen in self.people), bodies=tuple(seen.person for seen in self.bodies)
                ),
                quality=self.sight,
                happened_at=at,
                calls_attention=False,
            ),
        )

    def destinations(self) -> tuple[SpotId, ...]:
        here = self.spot.spot_id
        return tuple(
            dict.fromkeys(
                far for far in (shown.passage.far_end_from(here) for shown in self.passages) if far is not None
            )
        )

    def scene_with(
        self,
        texts: SurroundingsTexts,
        names: NamesInScene,
        words: WorldWords,
        clock: ClockWording,
    ) -> Scene:
        described = self._described_with(texts, names, words, clock).for_being()
        return Scene(here=Here(place=self.spot.name.text, heading=texts.scene.heading.text, text=described))

    def _described_with(
        self,
        texts: SurroundingsTexts,
        names: NamesInScene,
        words: WorldWords,
        clock: ClockWording,
    ) -> TextWithAssignedPeople:
        # 名前は行動の選択肢の候補と同じものを使う。場面の文で見た名前を、そのまま候補から選べるようにするため (D2226)。
        wording = texts.scene
        description = self.spot.description.text if self.shows_description else wording.pitch_dark.text
        written = [
            wording.description.format(description=description),
            *self.conditions.lines(wording, words, clock),
            *self._destination_lines(wording, names),
            *self._object_lines(wording),
        ]
        lines = [_letters(line) for line in written]
        lines += _listed(wording.ground_items, _counted(self.ground_items, names, wording.count_mark))
        if not self.people and not self.bodies:
            return TextWithAssignedPeople("\n".join(lines), {})
        people = texts.scene_as_seen(
            people=tuple(seen.person for seen in self.people), bodies=tuple(seen.person for seen in self.bodies)
        )
        return TextWithAssignedPeople("\n".join((*lines, people.template)), people.people)

    def _destination_lines(self, wording: SceneTexts, names: NamesInScene) -> list[str]:
        here = self.spot.spot_id
        lines = []
        for shown in self.passages:
            far = shown.passage.far_end_from(here)
            if far is None:
                continue
            state = shown.passage.state(shown.state)
            status = wording.passable if state.traversable else wording.impassable.format(state=state.display_name.text)
            lines.append(
                wording.destination.format(
                    passage=shown.passage.name.text, spot=names.spot_name(far).text, status=status
                )
            )
        return [wording.destinations, *lines] if lines else []

    def _object_lines(self, wording: SceneTexts) -> list[str]:
        # 何も無いのと、暗くて見えないのとを、同じ沈黙に潰さない。暗さで消えた物があるかもしれないと分からないと、探し回って時間を使うため
        dark = not _RULES[self.sight].shows_objects_unseen_in_dark
        if not self.objects:
            return [wording.no_objects_in_dark if dark else wording.no_objects]
        return [
            wording.objects,
            *([wording.objects_in_dark] if dark else []),
            *map(_object_line_in(wording), self.objects),
        ]


def _letters(text: str) -> str:
    return TextWithUnassignedPeople.literal(text).template


def _object_line_in(wording: SceneTexts) -> Callable[[SeenObject], str]:
    def line(seen: SeenObject) -> str:
        name, description = seen.declaration.name.text, seen.declaration.description.text
        if isinstance(seen.look, NoLook):
            return wording.object_without_look.format(object=name, description=description)
        return wording.object.format(object=name, look=seen.look.text, description=description)

    return line


def _counted(items: tuple[ItemInstanceId, ...], names: NamesInScene, mark: DisplayName) -> tuple[str, ...]:
    counts: dict[str, int] = {}
    for item in items:
        name = names.item_name(item).text
        counts[name] = counts.get(name, 0) + 1
    return tuple(name if count == 1 else f"{name} {mark.text}{count}" for name, count in counts.items())


def _listed(heading: DisplayName, entries: tuple[str, ...]) -> list[str]:
    if not entries:
        return []
    return [_letters(heading.text), *(_letters(f"- {entry}") for entry in entries)]


def _present(seen: Iterable[SeenPerson | None]) -> tuple[SeenPerson, ...]:
    return tuple(person for person in seen if person is not None)
