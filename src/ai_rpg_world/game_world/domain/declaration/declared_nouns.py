from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Generic, TypeVar

from ai_rpg_world.game_world.domain.declaration.character import (
    CharacterDeclaration,
    GroupDeclaration,
    GroupingDeclaration,
)
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
from ai_rpg_world.game_world.domain.exception.world_design_exception import UnknownNameFlaw
from ai_rpg_world.game_world.domain.value_object import SpotId

_Declaration = TypeVar("_Declaration")


class _DeclaredOfKind(Generic[_Declaration]):
    def __init__(
        self, kind: str, declarations: Iterable[_Declaration], name_of: Callable[[_Declaration], str]
    ) -> None:
        self._kind = kind
        self._declarations = tuple(declarations)
        self._by_name = {name_of(declaration): declaration for declaration in self._declarations}

    def __iter__(self):
        return iter(self._declarations)

    def get(self, name: str, at: DesignLocation) -> _Declaration:
        if name not in self._by_name:
            raise UnknownNameFlaw(DesignFlaw(at, f"{self._kind} {name!r} is not declared"))
        return self._by_name[name]


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
        self._flags = _DeclaredOfKind("flag", flags, lambda flag: flag.flag_id.value)
        self._spots = _DeclaredOfKind("spot", spots, lambda spot: spot.spot_id.value)
        self._passages = _DeclaredOfKind("passage", passages, lambda passage: passage.passage_id.value)
        self._objects = _DeclaredOfKind("object", objects, lambda obj: obj.object_id.value)
        self._item_specs = _DeclaredOfKind("item_spec", item_specs, lambda spec: spec.item_spec_id.value)
        self._groupings = _DeclaredOfKind("grouping", groupings, lambda grouping: grouping.grouping_id.value)
        self._groups = _DeclaredOfKind("group", groups, lambda group: group.group_id.value)
        self._characters = _DeclaredOfKind("character", characters, lambda character: character.person_id.value)
        self._world_stages = _DeclaredOfKind("world_stage", world_stages, lambda stage: stage.stage_id.value)
        self._group_decisions = _DeclaredOfKind(
            "group_decision", group_decisions, lambda decision: decision.decision_id.value
        )
        self._sections = _DeclaredOfKind("section", sections, lambda section: section.section_id.value)
        self._outcomes = _DeclaredOfKind("outcome", outcomes, lambda outcome: outcome.outcome_id.value)

    def flag(self, name: str, at: DesignLocation) -> FlagDeclaration:
        return self._flags.get(name, at)

    def spot(self, name: str, at: DesignLocation) -> SpotDeclaration:
        return self._spots.get(name, at)

    def passage(self, name: str, at: DesignLocation) -> PassageDeclaration:
        return self._passages.get(name, at)

    def object(self, name: str, at: DesignLocation) -> ObjectDeclaration:
        return self._objects.get(name, at)

    def object_state_key(self, object_name: str, key: str, at: DesignLocation) -> ObjectStateKeyDeclaration:
        obj = self._objects.get(object_name, at)
        for state_key in obj.state_keys:
            if state_key.key.value == key:
                return state_key
        raise UnknownNameFlaw(DesignFlaw(at, f"object {object_name!r} has no state key {key!r}"))

    def item_spec(self, name: str, at: DesignLocation) -> ItemSpecDeclaration:
        return self._item_specs.get(name, at)

    def group(self, name: str, at: DesignLocation) -> GroupDeclaration:
        return self._groups.get(name, at)

    def groups_in(self, grouping: GroupingDeclaration) -> tuple[GroupDeclaration, ...]:
        return tuple(group for group in self._groups if group.grouping.grouping_id == grouping.grouping_id)

    def character(self, name: str, at: DesignLocation) -> CharacterDeclaration:
        return self._characters.get(name, at)

    def world_stage(self, name: str, at: DesignLocation) -> WorldStageDeclaration:
        return self._world_stages.get(name, at)

    def group_decision(self, name: str, at: DesignLocation) -> GroupDecisionDeclaration:
        return self._group_decisions.get(name, at)

    def section(self, name: str, at: DesignLocation) -> SpotSectionDeclaration:
        return self._sections.get(name, at)

    def sections_at(self, spot: SpotId) -> tuple[SpotSectionDeclaration, ...]:
        return tuple(section for section in self._sections if section.spot_id == spot)

    def outcome(self, name: str, at: DesignLocation) -> OutcomeDeclaration:
        return self._outcomes.get(name, at)
