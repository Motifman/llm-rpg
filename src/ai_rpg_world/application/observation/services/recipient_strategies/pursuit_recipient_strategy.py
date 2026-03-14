"""追跡（Pursuit）イベントの観測配信先解決戦略"""

from typing import Any, List

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
    IWorldObjectToPlayerResolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitCancelledEvent,
    PursuitFailedEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class PursuitRecipientStrategy(IRecipientResolutionStrategy):
    """Pursuit 系イベントを actor/target に対応するプレイヤーへ配信する。"""

    _STRATEGY_KEY = "pursuit"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        world_object_to_player_resolver: IWorldObjectToPlayerResolver,
    ) -> None:
        self._registry = observed_event_registry
        self._world_object_to_player_resolver = world_object_to_player_resolver

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        if not self.supports(event):
            return []

        recipients: List[PlayerId] = []
        actor_player_id = self._resolve_player_id(event.actor_id)
        if actor_player_id is not None:
            recipients.append(actor_player_id)

        target_player_id = self._resolve_player_id(event.target_id)
        if target_player_id is not None:
            recipients.append(target_player_id)

        return recipients

    def _resolve_player_id(self, object_id: WorldObjectId) -> PlayerId | None:
        return self._world_object_to_player_resolver.resolve_player_id(object_id)
