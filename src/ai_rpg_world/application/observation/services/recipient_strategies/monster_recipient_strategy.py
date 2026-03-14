"""モンスター系イベントの観測配信先解決戦略"""

from typing import Any, List, Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IPlayerAudienceQueryPort,
    IRecipientResolutionStrategy,
    IWorldObjectToPlayerResolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.monster.event.monster_events import (
    ActorStateChangedEvent,
    BehaviorStuckEvent,
    MonsterCreatedEvent,
    MonsterDamagedEvent,
    MonsterDecidedToInteractEvent,
    MonsterDecidedToMoveEvent,
    MonsterDecidedToUseSkillEvent,
    MonsterDiedEvent,
    MonsterEvadedEvent,
    MonsterFedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent,
    MonsterRespawnedEvent,
    MonsterSpawnedEvent,
    TargetLostEvent,
    TargetSpottedEvent,
)
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class MonsterRecipientStrategy(IRecipientResolutionStrategy):
    """モンスターイベントの配信先を解決する。基本は「同一スポットのプレイヤー」＋必要なら攻撃者本人。"""

    _STRATEGY_KEY = "monster"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        player_audience_query: IPlayerAudienceQueryPort,
        physical_map_repository: PhysicalMapRepository,
        world_object_to_player_resolver: IWorldObjectToPlayerResolver,
        monster_repository: Optional[MonsterRepository] = None,
    ) -> None:
        self._registry = observed_event_registry
        self._player_audience_query = player_audience_query
        self._physical_map_repository = physical_map_repository
        self._world_object_to_player_resolver = world_object_to_player_resolver
        self._monster_repository = monster_repository

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        recipients: List[PlayerId] = []

        def add_all_at_spot(spot_id: Optional[SpotId]) -> None:
            if spot_id is None:
                return
            for pid in self._player_audience_query.players_at_spot(spot_id):
                recipients.append(pid)

        if isinstance(event, (MonsterSpawnedEvent, MonsterRespawnedEvent)):
            add_all_at_spot(event.spot_id)
            return recipients

        if isinstance(event, MonsterDiedEvent):
            add_all_at_spot(event.spot_id or self._spot_id_from_monster(event.aggregate_id))
            if event.killer_player_id is not None:
                recipients.append(event.killer_player_id)
            return recipients

        if isinstance(event, MonsterDamagedEvent):
            add_all_at_spot(self._spot_id_from_monster(event.aggregate_id))
            if event.attacker_id is not None:
                pid = self._world_object_to_player_resolver.resolve_player_id(event.attacker_id)
                if pid is not None:
                    recipients.append(pid)
            return recipients

        if isinstance(event, (MonsterEvadedEvent, MonsterHealedEvent)):
            add_all_at_spot(self._spot_id_from_monster(event.aggregate_id))
            return recipients

        if isinstance(event, MonsterMpRecoveredEvent):
            return recipients

        if isinstance(event, (MonsterDecidedToMoveEvent, MonsterDecidedToUseSkillEvent, MonsterDecidedToInteractEvent)):
            return recipients

        if isinstance(event, MonsterFedEvent):
            # actor_id が属する spot にいるプレイヤーへ
            add_all_at_spot(self._spot_id_from_world_object(event.actor_id))
            return recipients

        if isinstance(event, ActorStateChangedEvent):
            add_all_at_spot(self._spot_id_from_world_object(event.actor_id))
            return recipients

        if isinstance(event, (TargetSpottedEvent, TargetLostEvent, BehaviorStuckEvent)):
            return recipients

        # MonsterCreated は通知しない/配信先なし（レジストリ登録しても Resolver が空にできるが、ここでは空）
        return []

    def _spot_id_from_world_object(self, object_id) -> Optional[SpotId]:
        return self._physical_map_repository.find_spot_id_by_object_id(object_id)

    def _spot_id_from_monster(self, monster_id) -> Optional[SpotId]:
        if self._monster_repository is None:
            return None
        monster = self._monster_repository.find_by_id(monster_id)
        if monster is None:
            return None
        return monster.spot_id

