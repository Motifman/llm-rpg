from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId

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
