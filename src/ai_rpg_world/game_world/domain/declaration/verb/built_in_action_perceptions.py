from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from typing_extensions import assert_never

from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, Shout, SpeechReach, Whisper
from ai_rpg_world.game_world.domain.declaration.verb.built_in_perception_row import BuiltInPerceptionRow
from ai_rpg_world.game_world.domain.declaration.verb.noticed_on_waking import NoticedOnWaking
from ai_rpg_world.game_world.domain.declaration.verb.perception_declaration import PerceptionDeclaration
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import (
    NotBuiltInActionPerceptionException,
    TargetTextNotFittingTargetException,
    TargetTextWithoutTargetException,
    UnfilledNameInBuiltInActionPerceptionException,
)
from ai_rpg_world.game_world.domain.perception import NoTarget
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules


@final
@dataclass(frozen=True)
class BuiltInActionPerceptions:
    by_kind: Mapping[ActionKind, PerceptionDeclaration]
    whisper: PerceptionDeclaration
    ordinary_voice: PerceptionDeclaration
    shout: PerceptionDeclaration
    arrival: PerceptionDeclaration

    def __post_init__(self) -> None:
        not_built_in = sorted(kind.name for kind in self.by_kind.keys() - BuiltInPerceptionRow.kinds())
        if not_built_in:
            raise NotBuiltInActionPerceptionException(
                f"BuiltInActionPerceptions.by_kind must not declare {not_built_in}, which are not perceived through it"
            )
        for row, perception in self.rows():
            unfilled = sorted(perception.placeholders() - row.nameable)
            if unfilled:
                raise UnfilledNameInBuiltInActionPerceptionException(
                    f"the {row.name} perception can name only {sorted(row.nameable)}, but names {unfilled}"
                )
            if isinstance(perception.target, NoTarget):
                continue
            if not row.has_target:
                raise TargetTextWithoutTargetException(
                    f"the {row.name} perception has no target to tell, but writes a target text"
                )
            if row.target_is_down != isinstance(perception.target, NoticedOnWaking):
                raise TargetTextNotFittingTargetException(
                    f"the {row.name} perception tells its target only "
                    + ("what is noticed on waking" if row.target_is_down else "what is seen")
                )
        object.__setattr__(self, "by_kind", MappingProxyType(dict(self.by_kind)))

    def rows(self) -> tuple[tuple[BuiltInPerceptionRow, PerceptionDeclaration], ...]:
        return (
            *((BuiltInPerceptionRow.of_kind(kind), perception) for kind, perception in self.by_kind.items()),
            (BuiltInPerceptionRow.whisper(), self.whisper),
            (BuiltInPerceptionRow.speak(), self.ordinary_voice),
            (BuiltInPerceptionRow.shout(), self.shout),
            (BuiltInPerceptionRow.arrival(), self.arrival),
        )

    def speech(self, reach: SpeechReach) -> PerceptionDeclaration:
        if isinstance(reach, Whisper):
            return self.whisper
        if isinstance(reach, OrdinaryVoice):
            return self.ordinary_voice
        if isinstance(reach, Shout):
            return self.shout
        assert_never(reach)

    def flaws_for(self, rules: WorldRules, at: DesignLocation) -> list[DesignFlaw]:
        performable = BuiltInPerceptionRow.kinds()
        if not rules.allows_tending():
            performable -= {ActionKind.TEND}
        missing = sorted(kind.name for kind in performable - self.by_kind.keys())
        if missing:
            return [DesignFlaw(at, f"lacks how {missing} are perceived")]
        return []
