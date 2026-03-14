"""戦闘（HitBox）イベントの観測配信先解決戦略"""

from typing import Any, List, Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
    IWorldObjectToPlayerResolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxDeactivatedEvent,
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
    HitBoxObstacleCollidedEvent,
)
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class CombatRecipientStrategy(IRecipientResolutionStrategy):
    """HitBox 系イベントを、関係者プレイヤー（owner/target）へ配信する。"""

    _STRATEGY_KEY = "combat"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        world_object_to_player_resolver: IWorldObjectToPlayerResolver,
        hit_box_repository: Optional[HitBoxRepository] = None,
    ) -> None:
        self._registry = observed_event_registry
        self._world_object_to_player_resolver = world_object_to_player_resolver
        self._hit_box_repository = hit_box_repository

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        recipients: List[PlayerId] = []

        def add_player_by_object_id(object_id: WorldObjectId | None) -> None:
            if object_id is None:
                return
            pid = self._world_object_to_player_resolver.resolve_player_id(object_id)
            if pid is not None:
                recipients.append(pid)

        if isinstance(event, HitBoxHitRecordedEvent):
            add_player_by_object_id(event.owner_id)
            add_player_by_object_id(event.target_id)
            return recipients

        if isinstance(event, HitBoxCreatedEvent):
            return []

        if isinstance(event, (HitBoxMovedEvent, HitBoxDeactivatedEvent, HitBoxObstacleCollidedEvent)):
            return []

        return []

