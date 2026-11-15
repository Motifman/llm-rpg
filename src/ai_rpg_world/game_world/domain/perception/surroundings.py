from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, final

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
from ai_rpg_world.game_world.domain.people import PersonRef, Unidentified
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_outcome import NotPerceived, Perceived
from ai_rpg_world.game_world.domain.value_object import DescriptionText, PersonId, SpotId, SpotSectionId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts.location import OpenArea
from ai_rpg_world.game_world.domain.whereabouts.passage_in_state import PassageInState

if TYPE_CHECKING:
    # 実行時に import すると循環する。
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SurroundingsTexts
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
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


class SurroundingsSenses(Protocol):
    def lighting_at(self, spot: SpotId) -> Lighting: ...

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

    @classmethod
    def seen_by(cls, perceiver: Perceiver, senses: SurroundingsSenses) -> VisibleSurroundings | NothingInView:
        spot = perceiver.spot_in_view()
        if isinstance(spot, NothingInView):
            return spot
        return cls.seen_with(perceiver.sight_in(senses.lighting_at(spot)), senses.contents_at(spot))

    @classmethod
    def seen_with(cls, sight: SightQuality, contents: SpotContents) -> VisibleSurroundings:
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
        )

    def perceived_by(self, viewer: PersonId, texts: SurroundingsTexts, at: WorldTick) -> Perceived | NotPerceived:
        if isinstance(self.sight, SeesNothing) or not (self.people or self.bodies):
            return NotPerceived()
        return Perceived(
            perceiver=viewer,
            text=texts.scene_as_seen(
                people=tuple(seen.person for seen in self.people), bodies=tuple(seen.person for seen in self.bodies)
            ),
            quality=self.sight,
            happened_at=at,
            calls_attention=False,
        )


def _present(seen: Iterable[SeenPerson | None]) -> tuple[SeenPerson, ...]:
    return tuple(person for person in seen if person is not None)
