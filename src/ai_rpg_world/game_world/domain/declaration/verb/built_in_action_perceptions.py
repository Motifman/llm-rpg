from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.declaration.verb.perception_declaration import PerceptionDeclaration
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import NotBuiltInActionPerceptionException
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


@final
@dataclass(frozen=True)
class BuiltInActionPerceptions:
    by_kind: Mapping[ActionKind, PerceptionDeclaration]

    def __post_init__(self) -> None:
        not_built_in = sorted(kind.name for kind in self.by_kind.keys() & _KINDS_NOT_PERCEIVED_THROUGH_THIS_TABLE)
        if not_built_in:
            raise NotBuiltInActionPerceptionException(
                f"BuiltInActionPerceptions.by_kind must not declare {not_built_in}, which are not perceived through it"
            )
        object.__setattr__(self, "by_kind", MappingProxyType(dict(self.by_kind)))

    def flaws_for(self, rules: WorldRules, at: DesignLocation) -> list[DesignFlaw]:
        performable = frozenset(ActionKind) - _KINDS_NOT_PERCEIVED_THROUGH_THIS_TABLE
        if not rules.allows_tending():
            performable -= {ActionKind.TEND}
        missing = sorted(kind.name for kind in performable - self.by_kind.keys())
        if missing:
            return [DesignFlaw(at, f"lacks how {missing} are perceived")]
        return []
