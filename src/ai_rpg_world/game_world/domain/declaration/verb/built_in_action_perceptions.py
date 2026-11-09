from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.action.speech import Shout, SpeechReach, Whisper
from ai_rpg_world.game_world.domain.declaration.verb.perception_declaration import PerceptionDeclaration
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    NotBuiltInActionPerceptionException,
    UnfilledNameInBuiltInActionPerceptionException,
)
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules

_KINDS_NOT_PERCEIVED_THROUGH_THIS_TABLE = frozenset(
    {
        ActionKind.INTERACT_WITH_OBJECT,
        ActionKind.INTERACT_WITH_CARRIED_ITEM,
        ActionKind.INTERACT_WITH_PERSON,
        ActionKind.ENTER_SECTION,
        ActionKind.LEAVE_SECTION,
        ActionKind.ATTACK_MONSTER,
    }
)
_KINDS_PERCEIVED_BY_VOICE = frozenset({ActionKind.SPEAK})

_ACTOR = frozenset({"actor"})
_ACTOR_AND_TARGET = frozenset({"actor", "target"})
_NAMES_BY_KIND: Mapping[ActionKind, frozenset[str]] = {
    ActionKind.TRAVEL: _ACTOR | {"destination"},
    ActionKind.HAND_OVER: _ACTOR_AND_TARGET | {"item"},
    ActionKind.TEND: _ACTOR_AND_TARGET,
    ActionKind.PICK_UP: _ACTOR | {"item"},
    ActionKind.DROP: _ACTOR | {"item"},
    ActionKind.USE_ITEM: _ACTOR | {"item"},
    ActionKind.HOLD: _ACTOR | {"item"},
    ActionKind.PUT_AWAY: _ACTOR | {"item"},
    ActionKind.LISTEN: _ACTOR,
    ActionKind.WAIT: _ACTOR,
    ActionKind.SEARCH: _ACTOR,
    ActionKind.CAST_BALLOT: _ACTOR,
}
_WHISPER_NAMES = _ACTOR_AND_TARGET | {"speech"}
_VOICE_NAMES = _ACTOR | {"speech"}
_ARRIVAL_NAMES = _ACTOR | {"origin"}


@final
@dataclass(frozen=True)
class BuiltInActionPerceptions:
    by_kind: Mapping[ActionKind, PerceptionDeclaration]
    whisper: PerceptionDeclaration
    ordinary_voice: PerceptionDeclaration
    shout: PerceptionDeclaration
    arrival: PerceptionDeclaration

    def __post_init__(self) -> None:
        not_built_in = sorted(
            kind.name
            for kind in self.by_kind.keys() & (_KINDS_NOT_PERCEIVED_THROUGH_THIS_TABLE | _KINDS_PERCEIVED_BY_VOICE)
        )
        if not_built_in:
            raise NotBuiltInActionPerceptionException(
                f"BuiltInActionPerceptions.by_kind must not declare {not_built_in}, which are not perceived through it"
            )
        rows = [
            *((kind.name, perception, _NAMES_BY_KIND[kind]) for kind, perception in self.by_kind.items()),
            ("whisper", self.whisper, _WHISPER_NAMES),
            ("ordinary_voice", self.ordinary_voice, _VOICE_NAMES),
            ("shout", self.shout, _VOICE_NAMES),
            ("arrival", self.arrival, _ARRIVAL_NAMES),
        ]
        for row, perception, fillable in rows:
            unfilled = sorted(perception.placeholders() - fillable)
            if unfilled:
                raise UnfilledNameInBuiltInActionPerceptionException(
                    f"the {row} perception can name only {sorted(fillable)}, but names {unfilled}"
                )
        object.__setattr__(self, "by_kind", MappingProxyType(dict(self.by_kind)))

    def speech(self, reach: SpeechReach) -> PerceptionDeclaration:
        if isinstance(reach, Whisper):
            return self.whisper
        if isinstance(reach, Shout):
            return self.shout
        return self.ordinary_voice

    def flaws_for(self, rules: WorldRules, at: DesignLocation) -> list[DesignFlaw]:
        performable = frozenset(ActionKind) - _KINDS_NOT_PERCEIVED_THROUGH_THIS_TABLE - _KINDS_PERCEIVED_BY_VOICE
        if not rules.allows_tending():
            performable -= {ActionKind.TEND}
        missing = sorted(kind.name for kind in performable - self.by_kind.keys())
        if missing:
            return [DesignFlaw(at, f"lacks how {missing} are perceived")]
        return []
