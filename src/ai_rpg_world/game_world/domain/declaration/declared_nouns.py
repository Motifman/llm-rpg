from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from typing import Any, Generic, TypeVar

from ai_rpg_world.game_world.domain.declaration.character import (
    CharacterDeclaration,
    GroupDeclaration,
    GroupingDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.initial_world import StartingPerson
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    ObjectDeclaration,
    ObjectStateKeyDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.progress import (
    FlagDeclaration,
    GroupDecisionDeclaration,
    OutcomeDeclaration,
    WorldStageDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.spot import (
    PassageDeclaration,
    SpotDeclaration,
    SpotSectionDeclaration,
)
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.world_design_exception import UnknownNameFlaw, WorldDesignFlawsException
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    GroupDecisionId,
    GroupId,
    GroupingId,
    HitPoints,
    ItemSpecId,
    ObjectId,
    OutcomeId,
    PassageId,
    PersonId,
    SpotId,
    SpotSectionId,
    WorldStageId,
)

_Declaration = TypeVar("_Declaration")


class _DeclaredOfKind(Generic[_Declaration]):
    def __init__(self, kind: str, id_field: str, declarations: Iterable[_Declaration]) -> None:
        self.kind = kind
        self._id_field = id_field
        self._declarations = tuple(declarations)
        self._by_name = {self.name_of(declaration): declaration for declaration in self._declarations}

    def __iter__(self) -> Iterator[_Declaration]:
        return iter(self._declarations)

    def name_of(self, declaration: _Declaration) -> str:
        declared_id: Any = getattr(declaration, self._id_field)
        return str(declared_id.value)

    def get(self, name: str, at: DesignLocation) -> _Declaration:
        if name not in self._by_name:
            raise UnknownNameFlaw(self._unknown(name, at))
        return self._by_name[name]

    def find(self, name: str) -> _Declaration | None:
        return self._by_name.get(name)

    def with_id(self, declared_id: Any) -> _Declaration:
        self.require(declared_id)
        return self._by_name[str(declared_id.value)]

    def require(self, declared_id: Any) -> None:
        name = str(declared_id.value)
        if name not in self._by_name:
            raise UndeclaredNounException(f"{self.kind} {name!r} is not declared")

    def flaws_if_unknown(self, name: str, at: DesignLocation) -> list[DesignFlaw]:
        if name in self._by_name:
            return []
        return [self._unknown(name, at)]

    def duplicated_name_flaws(self) -> list[DesignFlaw]:
        counts = Counter(self.name_of(declaration) for declaration in self._declarations)
        return [
            DesignFlaw(
                DesignLocation(self.kind, name, self._id_field), f"{self.kind} {name!r} is declared more than once"
            )
            for name, count in counts.items()
            if count > 1
        ]

    def location(self, declaration: _Declaration, field: str) -> DesignLocation:
        return DesignLocation(self.kind, self.name_of(declaration), field)

    def _unknown(self, name: str, at: DesignLocation) -> DesignFlaw:
        return DesignFlaw(at, f"{self.kind} {name!r} is not declared")


class DeclaredNouns:
    def __init__(
        self,
        flags: Iterable[FlagDeclaration],
        spots: Iterable[SpotDeclaration],
        passages: Iterable[PassageDeclaration],
        objects: Iterable[ObjectDeclaration],
        item_specs: Iterable[ItemSpecDeclaration],
        groupings: Iterable[GroupingDeclaration],
        groups: Iterable[GroupDeclaration],
        characters: Iterable[CharacterDeclaration],
        world_stages: Iterable[WorldStageDeclaration],
        group_decisions: Iterable[GroupDecisionDeclaration],
        sections: Iterable[SpotSectionDeclaration],
        outcomes: Iterable[OutcomeDeclaration],
    ) -> None:
        self._flags = _DeclaredOfKind("flag", "flag_id", flags)
        self._spots = _DeclaredOfKind("spot", "spot_id", spots)
        self._passages = _DeclaredOfKind("passage", "passage_id", passages)
        self._objects = _DeclaredOfKind("object", "object_id", objects)
        self._item_specs = _DeclaredOfKind("item_spec", "item_spec_id", item_specs)
        self._groupings = _DeclaredOfKind("grouping", "grouping_id", groupings)
        self._groups = _DeclaredOfKind("group", "group_id", groups)
        self._characters = _DeclaredOfKind("character", "person_id", characters)
        self._world_stages = _DeclaredOfKind("world_stage", "stage_id", world_stages)
        self._group_decisions = _DeclaredOfKind("group_decision", "decision_id", group_decisions)
        self._sections = _DeclaredOfKind("section", "section_id", sections)
        self._outcomes = _DeclaredOfKind("outcome", "outcome_id", outcomes)
        flaws = [
            *self._duplicated_name_flaws(),
            *self._passage_flaws(),
            *self._object_flaws(),
            *self._section_flaws(),
            *self._group_flaws(),
            *self._character_flaws(),
        ]
        if flaws:
            raise WorldDesignFlawsException(flaws)

    def flag(self, name: str, at: DesignLocation) -> FlagDeclaration:
        return self._flags.get(name, at)

    def spot(self, name: str, at: DesignLocation) -> SpotDeclaration:
        return self._spots.get(name, at)

    def spot_of(self, spot_id: SpotId) -> SpotDeclaration:
        return self._spots.with_id(spot_id)

    def require_declared_spot(self, spot_id: SpotId) -> None:
        self._spots.require(spot_id)

    def passage(self, name: str, at: DesignLocation) -> PassageDeclaration:
        return self._passages.get(name, at)

    def passage_of(self, passage_id: PassageId) -> PassageDeclaration:
        return self._passages.with_id(passage_id)

    def require_declared_passage(self, passage_id: PassageId) -> None:
        self._passages.require(passage_id)

    def object(self, name: str, at: DesignLocation) -> ObjectDeclaration:
        return self._objects.get(name, at)

    def object_of(self, object_id: ObjectId) -> ObjectDeclaration:
        return self._objects.with_id(object_id)

    def object_flaws_if_unknown(self, object_id: ObjectId, at: DesignLocation) -> list[DesignFlaw]:
        return self._objects.flaws_if_unknown(object_id.value, at)

    def object_state_key(self, object_name: str, key: str, at: DesignLocation) -> ObjectStateKeyDeclaration:
        obj = self._objects.get(object_name, at)
        for state_key in obj.state_keys:
            if state_key.key.value == key:
                return state_key
        raise UnknownNameFlaw(DesignFlaw(at, f"object {object_name!r} has no state key {key!r}"))

    def item_spec(self, name: str, at: DesignLocation) -> ItemSpecDeclaration:
        return self._item_specs.get(name, at)

    def item_spec_of(self, item_spec_id: ItemSpecId) -> ItemSpecDeclaration:
        return self._item_specs.with_id(item_spec_id)

    def group(self, name: str, at: DesignLocation) -> GroupDeclaration:
        return self._groups.get(name, at)

    def groups_in(self, grouping: GroupingDeclaration) -> tuple[GroupDeclaration, ...]:
        return tuple(group for group in self._groups if group.grouping.grouping_id == grouping.grouping_id)

    def group_of(self, group_id: GroupId) -> GroupDeclaration:
        return self._groups.with_id(group_id)

    def character(self, name: str, at: DesignLocation) -> CharacterDeclaration:
        return self._characters.get(name, at)

    def character_of(self, person: PersonId) -> CharacterDeclaration:
        return self._characters.with_id(person)

    def require_declared_character(self, person: PersonId) -> None:
        self._characters.require(person)

    def all_characters(self) -> tuple[CharacterDeclaration, ...]:
        return tuple(self._characters)

    def world_stage(self, name: str, at: DesignLocation) -> WorldStageDeclaration:
        return self._world_stages.get(name, at)

    def world_stage_of(self, stage_id: WorldStageId) -> WorldStageDeclaration:
        return self._world_stages.with_id(stage_id)

    def group_decision(self, name: str, at: DesignLocation) -> GroupDecisionDeclaration:
        return self._group_decisions.get(name, at)

    def group_decision_of(self, decision_id: GroupDecisionId) -> GroupDecisionDeclaration:
        return self._group_decisions.with_id(decision_id)

    def section(self, name: str, at: DesignLocation) -> SpotSectionDeclaration:
        return self._sections.get(name, at)

    def section_of(self, section_id: SpotSectionId) -> SpotSectionDeclaration:
        return self._sections.with_id(section_id)

    def sections_at(self, spot: SpotId) -> tuple[SpotSectionDeclaration, ...]:
        return tuple(section for section in self._sections if section.spot_id == spot)

    def all_flags(self) -> tuple[FlagDeclaration, ...]:
        return tuple(self._flags)

    def all_spots(self) -> tuple[SpotDeclaration, ...]:
        return tuple(self._spots)

    def all_passages(self) -> tuple[PassageDeclaration, ...]:
        return tuple(self._passages)

    def all_objects(self) -> tuple[ObjectDeclaration, ...]:
        return tuple(self._objects)

    def initially_raised_flags(self) -> frozenset[FlagDeclaration]:
        return frozenset(flag for flag in self._flags if flag.initially_raised)

    def starting_people(self, default_hp: HitPoints, default_pack_capacity: Capacity) -> tuple[StartingPerson, ...]:
        return tuple(
            StartingPerson(
                person=character.person_id,
                spawn_spot=self._spots.with_id(character.spawn_spot),
                items=tuple(self._item_specs.with_id(item) for item in character.initial_items),
                held=tuple(self._item_specs.with_id(item) for item in character.initial_held),
                groups=tuple(self._groups.with_id(group) for group in character.initial_groups),
                knows=character.knows_at_start,
                hp=character.starting_hp(default_hp),
                pack_capacity=character.starting_pack_capacity(default_pack_capacity),
            )
            for character in self._characters
        )

    def all_sections(self) -> tuple[SpotSectionDeclaration, ...]:
        return tuple(self._sections)

    def all_group_decisions(self) -> tuple[GroupDecisionDeclaration, ...]:
        return tuple(self._group_decisions)

    def outcome(self, name: str, at: DesignLocation) -> OutcomeDeclaration:
        return self._outcomes.get(name, at)

    def outcome_of(self, outcome_id: OutcomeId) -> OutcomeDeclaration:
        return self._outcomes.with_id(outcome_id)

    def _duplicated_name_flaws(self) -> list[DesignFlaw]:
        kinds: tuple[_DeclaredOfKind[Any], ...] = (
            self._flags,
            self._spots,
            self._passages,
            self._objects,
            self._item_specs,
            self._groupings,
            self._groups,
            self._characters,
            self._world_stages,
            self._group_decisions,
            self._sections,
            self._outcomes,
        )
        return [flaw for kind in kinds for flaw in kind.duplicated_name_flaws()]

    def _passage_flaws(self) -> list[DesignFlaw]:
        return [
            flaw
            for passage in self._passages
            for index, end in enumerate(passage.ends)
            for flaw in self._spots.flaws_if_unknown(end.value, self._passages.location(passage, f"ends[{index}]"))
        ]

    def _object_flaws(self) -> list[DesignFlaw]:
        return [
            flaw
            for obj in self._objects
            for flaw in self._spots.flaws_if_unknown(obj.spot_id.value, self._objects.location(obj, "spot_id"))
        ]

    def _section_flaws(self) -> list[DesignFlaw]:
        flaws: list[DesignFlaw] = []
        for section in self._sections:
            flaws += self._spots.flaws_if_unknown(section.spot_id.value, self._sections.location(section, "spot_id"))
            for index, object_id in enumerate(section.reachable_objects):
                at = self._sections.location(section, f"reachable_objects[{index}]")
                obj = self._objects.find(object_id.value)
                if obj is None:
                    flaws += self._objects.flaws_if_unknown(object_id.value, at)
                elif obj.spot_id != section.spot_id:
                    flaws.append(
                        DesignFlaw(
                            at,
                            f"object {object_id.value!r} is at spot {obj.spot_id.value!r}, "
                            f"not {section.spot_id.value!r}",
                        )
                    )
        return flaws

    def _group_flaws(self) -> list[DesignFlaw]:
        flaws: list[DesignFlaw] = []
        for group in self._groups:
            at = self._groups.location(group, "grouping")
            name = group.grouping.grouping_id.value
            declared = self._groupings.find(name)
            if declared is None:
                flaws += self._groupings.flaws_if_unknown(name, at)
            elif declared != group.grouping:
                flaws.append(DesignFlaw(at, f"grouping {name!r} differs from its declaration"))
        return flaws

    def _character_flaws(self) -> list[DesignFlaw]:
        flaws: list[DesignFlaw] = []
        for character in self._characters:
            flaws += self._spots.flaws_if_unknown(
                character.spawn_spot.value, self._characters.location(character, "spawn_spot")
            )
            for index, item in enumerate(character.initial_items):
                flaws += self._item_specs.flaws_if_unknown(
                    item.value, self._characters.location(character, f"initial_items[{index}]")
                )
            flaws += self._initial_group_flaws(character)
            for index, person in enumerate(character.knows_at_start):
                flaws += self._characters.flaws_if_unknown(
                    person.value, self._characters.location(character, f"knows_at_start[{index}]")
                )
        return flaws

    def _initial_group_flaws(self, character: CharacterDeclaration) -> list[DesignFlaw]:
        flaws: list[DesignFlaw] = []
        joined: dict[GroupingId, GroupDeclaration] = {}
        for index, group_id in enumerate(character.initial_groups):
            at = self._characters.location(character, f"initial_groups[{index}]")
            group = self._groups.find(group_id.value)
            if group is None:
                flaws += self._groups.flaws_if_unknown(group_id.value, at)
                continue
            grouping_id = group.grouping.grouping_id
            if grouping_id in joined:
                flaws.append(
                    DesignFlaw(
                        at,
                        f"group {group_id.value!r} and group {joined[grouping_id].group_id.value!r} "
                        f"both belong to grouping {grouping_id.value!r}",
                    )
                )
                continue
            joined[grouping_id] = group
        return flaws
