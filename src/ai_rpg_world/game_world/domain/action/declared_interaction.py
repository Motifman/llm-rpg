from __future__ import annotations

from typing import Protocol

from ai_rpg_world.game_world.domain.action.action_attempt import ActorRequirement, Exertion
from ai_rpg_world.game_world.domain.action.argument_declaration import ArgumentDeclaration
from ai_rpg_world.game_world.domain.value_object import InteractionId


class DeclaredInteraction(Protocol):
    @property
    def interaction_id(self) -> InteractionId: ...

    @property
    def exertion(self) -> Exertion: ...

    @property
    def actor_requirement(self) -> ActorRequirement: ...

    @property
    def allows_stealth(self) -> bool: ...

    @property
    def reaches_unseen(self) -> bool: ...

    @property
    def arguments(self) -> tuple[ArgumentDeclaration, ...]: ...
