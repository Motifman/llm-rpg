from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.rule_placement import RulePlacement
from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind

_ACTOR = "actor"
_TARGET = "target"


@final
@dataclass(frozen=True)
class BuiltInPerceptionRow:
    name: str
    has_target: bool
    names_of_things: frozenset[str]

    @classmethod
    def of_kind(cls, kind: ActionKind) -> BuiltInPerceptionRow:
        return _ROW_OF_KIND[kind]

    @classmethod
    def kinds(cls) -> frozenset[ActionKind]:
        return frozenset(_ROW_OF_KIND)

    @classmethod
    def whisper(cls) -> BuiltInPerceptionRow:
        return _WHISPER

    @classmethod
    def speak(cls) -> BuiltInPerceptionRow:
        return _SPEAK

    @classmethod
    def shout(cls) -> BuiltInPerceptionRow:
        return _SHOUT

    @classmethod
    def arrival(cls) -> BuiltInPerceptionRow:
        return _ARRIVAL

    @property
    def nameable(self) -> frozenset[str]:
        people = {_ACTOR, _TARGET} if self.has_target else {_ACTOR}
        return self.names_of_things | people

    def placement(self, location: DesignLocation) -> RulePlacement:
        if self.has_target:
            return RulePlacement.in_person_interaction(location, frozenset())
        return RulePlacement.in_action(location, frozenset())


_ROW_OF_KIND: Mapping[ActionKind, BuiltInPerceptionRow] = {
    kind: BuiltInPerceptionRow(name=kind.name, has_target=has_target, names_of_things=frozenset(names_of_things))
    for kind, has_target, names_of_things in (
        (ActionKind.TRAVEL, False, {"destination"}),
        (ActionKind.HAND_OVER, True, {"item"}),
        (ActionKind.TEND, True, set()),
        (ActionKind.PICK_UP, False, {"item"}),
        (ActionKind.DROP, False, {"item"}),
        (ActionKind.USE_ITEM, False, {"item"}),
        (ActionKind.HOLD, False, {"item"}),
        (ActionKind.PUT_AWAY, False, {"item"}),
        (ActionKind.LISTEN, False, set()),
        (ActionKind.WAIT, False, set()),
        (ActionKind.SEARCH, False, set()),
        (ActionKind.CAST_BALLOT, False, set()),
    )
}
_WHISPER = BuiltInPerceptionRow(name="whisper", has_target=True, names_of_things=frozenset({"speech"}))
_SPEAK = BuiltInPerceptionRow(name="speak", has_target=False, names_of_things=frozenset({"speech"}))
_SHOUT = BuiltInPerceptionRow(name="shout", has_target=False, names_of_things=frozenset({"speech"}))
_ARRIVAL = BuiltInPerceptionRow(name="arrival", has_target=False, names_of_things=frozenset({"origin"}))
