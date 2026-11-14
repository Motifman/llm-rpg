from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.exception.condition_exception import NotDeclaredInThisWorldException
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, WorldStageId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns


@final
@dataclass(frozen=True)
class NoWorldStages:
    def allows(self, kind: ActionKind) -> bool:
        return True

    def allows_interaction(self, interaction: InteractionId) -> bool:
        return True

    def declaration_in(self, nouns: DeclaredNouns) -> NoWorldStages:
        return self

    def is_declared(self) -> bool:
        return False

    def current(self) -> WorldStageId:
        raise NotDeclaredInThisWorldException("this world declares no world stages")

    def entered_at(self) -> WorldTick:
        raise NotDeclaredInThisWorldException("this world declares no world stages")
