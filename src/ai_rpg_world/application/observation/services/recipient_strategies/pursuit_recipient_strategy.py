"""追跡（Pursuit）イベントの観測配信先解決戦略"""

from typing import Any, List

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
    IWorldObjectToPlayerResolver,
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

    def __init__(
        self, world_object_to_player_resolver: IWorldObjectToPlayerResolver
    ) -> None:
        self._world_object_to_player_resolver = world_object_to_player_resolver

    def supports(self, event: Any) -> bool:
        return isinstance(
            event,
            (
                PursuitStartedEvent,
                PursuitUpdatedEvent,
                PursuitFailedEvent,
                PursuitCancelledEvent,
            ),
        )

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
