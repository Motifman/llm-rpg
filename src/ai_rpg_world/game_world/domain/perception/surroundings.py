from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.declaration.object_and_item.object_declaration import ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.exception.surroundings_exception import (
    HeldItemNotCarriedException,
    ThingFromAnotherSpotException,
    UnrevealedThingNotDeclaredHiddenException,
)
from ai_rpg_world.game_world.domain.lighting import SeesClearly, SeesNothing, SeesShapes, SightQuality
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import PersonRef, Unidentified
from ai_rpg_world.game_world.domain.value_object import SpotSectionId
from ai_rpg_world.game_world.domain.whereabouts.location import OpenArea
from ai_rpg_world.game_world.domain.whereabouts.passage_in_state import PassageInState


@final
@dataclass(frozen=True)
class _SightRule:
    shows_description: bool
    shows_people: bool
    identifies_people: bool
    shows_ground_items: bool
    shows_objects_unseen_in_dark: bool


_RULES: Mapping[SightQuality, _SightRule] = MappingProxyType(
    {
        SeesClearly(): _SightRule(
            shows_description=True,
            shows_people=True,
            identifies_people=True,
            shows_ground_items=True,
            shows_objects_unseen_in_dark=True,
        ),
        SeesShapes(): _SightRule(
            shows_description=True,
            shows_people=True,
            identifies_people=False,
            shows_ground_items=False,
            shows_objects_unseen_in_dark=False,
        ),
        SeesNothing(): _SightRule(
            shows_description=False,
            shows_people=False,
            identifies_people=False,
            shows_ground_items=False,
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
            visible_items=items,
        )


@final
@dataclass(frozen=True)
class ContainedObject:
    declaration: ObjectDeclaration
    revealed: bool

    def __post_init__(self) -> None:
        if not self.revealed and not self.declaration.appearance.hidden_until_revealed:
            raise UnrevealedThingNotDeclaredHiddenException(
                f"object {self.declaration.object_id.value} is not declared hidden but is unrevealed"
            )

    def is_seen_with(self, sight: SightQuality) -> bool:
        return self.revealed and (
            self.declaration.appearance.seen_in_dark or _RULES[sight].shows_objects_unseen_in_dark
        )


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


@final
@dataclass(frozen=True)
class VisibleSurroundings:
    spot: SpotDeclaration
    shows_description: bool
    passages: tuple[PassageInState, ...]
    sections: tuple[SpotSectionDeclaration, ...]
    objects: tuple[ObjectDeclaration, ...]
    ground_items: tuple[ItemInstanceId, ...]
    people: tuple[SeenPerson, ...]
    bodies: tuple[SeenPerson, ...]

    @classmethod
    def seen_with(cls, sight: SightQuality, contents: SpotContents) -> VisibleSurroundings:
        rule = _RULES[sight]
        return cls(
            spot=contents.spot,
            shows_description=rule.shows_description,
            passages=tuple(contained.passage for contained in contents.passages if contained.is_seen()),
            sections=contents.sections,
            objects=tuple(contained.declaration for contained in contents.objects if contained.is_seen_with(sight)),
            ground_items=contents.ground_items if rule.shows_ground_items else (),
            people=_present(person.seen_awake_with(sight) for person in contents.people),
            bodies=_present(body.seen_down_with(sight) for body in contents.bodies),
        )


def _present(seen: Iterable[SeenPerson | None]) -> tuple[SeenPerson, ...]:
    return tuple(person for person in seen if person is not None)
