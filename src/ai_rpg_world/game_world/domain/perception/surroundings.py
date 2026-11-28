from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from string import Formatter
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, final

from typing_extensions import assert_never

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
from ai_rpg_world.game_world.domain.perception.perceiver_in_world import perceiver_in_world
from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived
from ai_rpg_world.game_world.domain.perception.scene_conditions import SceneConditions
from ai_rpg_world.game_world.domain.perception.what_perceived_conveys import WhatPerceivedConveys
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
    from ai_rpg_world.game_world.domain.condition.aggregate_readings import PersonVitalsReading
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SceneTexts, SurroundingsTexts
    from ai_rpg_world.game_world.domain.declaration.time_and_weather.clock_wording import ClockWording
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
    from ai_rpg_world.game_world.domain.declaration.world_words import WorldWords
    from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
    from ai_rpg_world.game_world.domain.perception.oneself import Oneself
    from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueRule


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
class Up:
    looks: DisplayName | None


@final
@dataclass(frozen=True)
class Down:
    pass


@final
@dataclass(frozen=True)
class Dead:
    pass


PersonCondition = Up | Down | Dead


@final
@dataclass(frozen=True)
class SeenPerson:
    person: PersonRef | Unidentified
    section: SpotSectionId | OpenArea
    visible_items: tuple[ItemInstanceId, ...]
    condition: PersonCondition
    items_in_sight: bool


@final
@dataclass(frozen=True)
class PresentPerson:
    person: PersonRef
    section: SpotSectionId | OpenArea
    held_items: tuple[ItemInstanceId, ...]
    all_items: tuple[ItemInstanceId, ...]
    condition: PersonCondition

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
            condition=self.condition,
            items_in_sight=rule.shows_items,
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
            vitals = facts.vitals(occupant.person)
            present = PresentPerson(
                person=view.ref_of(occupant.person),
                section=section,
                held_items=inventory.held_items(),
                all_items=inventory.items(),
                condition=_condition_of(vitals, facts.rules().fatigue),
            )
            (people if vitals.can_act() else bodies).append(present)
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
    def seen_by_person(
        cls, person: PersonId, facts: WorldFacts, design: WorldDesign
    ) -> VisibleSurroundings | NothingInView:
        # surroundings_in_world は SpotContents をこのモジュールから import するので、頭で import すると循環する。
        from ai_rpg_world.game_world.domain.perception.surroundings_in_world import SurroundingsInWorld

        return cls.seen_by(
            perceiver_in_world(facts, person, attentive=False), SurroundingsInWorld(person, facts, design)
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
                addressed_to_perceiver=False,
                conveys=WhatPerceivedConveys.WHAT_HAPPENED,
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
        oneself: Oneself,
    ) -> Scene:
        described = self._described_with(texts, names, words, clock, oneself).for_being()
        return Scene(here=Here(place=self.spot.name.text, heading=texts.scene.heading.text, text=described))

    def _described_with(
        self,
        texts: SurroundingsTexts,
        names: NamesInScene,
        words: WorldWords,
        clock: ClockWording,
        oneself: Oneself,
    ) -> TextWithAssignedPeople:
        # 名前は行動の選択肢の候補と同じものを使う。場面の文で見た名前を、そのまま候補から選べるようにするため (D2226)。
        wording = texts.scene
        description = self.spot.description.text if self.shows_description else wording.pitch_dark.text
        written = [
            wording.description.format(description=description),
            *self.conditions.lines(wording, words, clock),
            *self._destination_lines(wording, names),
        ]
        lines = [_letters(line) for line in written]
        lines += self._object_lines(wording)
        lines += _listed(wording.ground_items, _counted(self.ground_items, names, wording.count_mark))
        holes: dict[str, PersonRef | Unidentified] = {}
        lines += self._people_lines(wording, names, holes)
        lines += [_letters(line) for line in oneself.lines(wording)]
        lines += oneself.doing_lines(wording, clock, holes)
        return TextWithAssignedPeople("\n".join(lines), holes)

    def _people_lines(
        self, wording: SceneTexts, names: NamesInScene, holes: dict[str, PersonRef | Unidentified]
    ) -> list[str]:
        everyone = (*self.people, *self.bodies)
        if not everyone:
            return [_letters(wording.no_people)]
        lines = [_letters(wording.people)]
        for seen in everyone:
            key = f"person_{len(holes) + 1}"
            holes[key] = seen.person
            condition, carried = _condition_and_carried(seen, wording, names)
            lines.append(
                _filled(
                    wording.person,
                    {"person": f"{{{key}}}", "condition": _letters(condition), "carried": _letters(carried)},
                )
            )
        return lines

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
            return [_letters(wording.no_objects_in_dark if dark else wording.no_objects)]
        lines = [_letters(wording.objects), *([_letters(wording.objects_in_dark)] if dark else [])]
        for seen in self.objects:
            lines.append(_letters(_object_line_in(wording)(seen)))
        return lines


def _filled(text: str, values: Mapping[str, str]) -> str:
    return "".join(
        _letters(literal) + ("" if name is None else values[name]) for literal, name, _, _ in Formatter().parse(text)
    )


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


def _condition_of(vitals: PersonVitalsReading, fatigue: FatigueRule) -> PersonCondition:
    if vitals.is_dead():
        return Dead()
    if not vitals.can_act():
        return Down()
    return Up(looks=fatigue.level_of(vitals.fatigue()).seen_as)


def _condition_and_carried(seen: SeenPerson, wording: SceneTexts, names: NamesInScene) -> tuple[str, str]:
    # 倒れている人が何を持ったままかは、起こしに行くか荷を引き受けるかを選ぶ材料になる。起きている人の荷は見せない
    match seen.condition:
        case Up(looks=DisplayName() as looks):
            return wording.person_looks.format(looks=looks.text), ""
        case Up():
            return "", ""
        case Down():
            return wording.person_down, _carried(seen, wording, names)
        case Dead():
            return wording.person_dead, _carried(seen, wording, names)
        case _:
            assert_never(seen.condition)


def _carried(seen: SeenPerson, wording: SceneTexts, names: NamesInScene) -> str:
    # 暗くて持ち物が見えないときに何も持っていないと書くと、持っていない事実と取り違えられる
    if not seen.items_in_sight:
        return ""
    if not seen.visible_items:
        return wording.carrying_nothing
    return wording.carried.format(
        items=wording.carried_joiner.join(names.item_name(item).text for item in seen.visible_items)
    )
