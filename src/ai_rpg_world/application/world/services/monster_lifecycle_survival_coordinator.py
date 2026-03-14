import logging
import random
from typing import Callable, List, Optional, Set

from ai_rpg_world.application.world.services.hunger_migration_policy import (
    HungerMigrationCandidate,
    HungerMigrationPolicy,
)
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.connected_spots_provider import (
    IConnectedSpotsProvider,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class MonsterLifecycleSurvivalCoordinator:
    """生存進行と hunger migration apply を束ねる coordinator。"""

    def __init__(
        self,
        monster_repository: MonsterRepository,
        physical_map_repository: PhysicalMapRepository,
        connected_spots_provider_getter: Callable[[], Optional[IConnectedSpotsProvider]],
        map_transition_service_getter: Callable[[], Optional[MapTransitionService]],
        hunger_migration_policy: HungerMigrationPolicy,
        spot_has_feed_for_monster: Callable[
            [PhysicalMapAggregate, MonsterAggregate, WorldTick], bool
        ],
        unit_of_work: UnitOfWork,
        logger: logging.Logger,
    ) -> None:
        self._monster_repository = monster_repository
        self._physical_map_repository = physical_map_repository
        self._connected_spots_provider_getter = connected_spots_provider_getter
        self._map_transition_service_getter = map_transition_service_getter
        self._hunger_migration_policy = hunger_migration_policy
        self._spot_has_feed_for_monster = spot_has_feed_for_monster
        self._unit_of_work = unit_of_work
        self._logger = logger

    def process_survival_for_spot(
        self,
        physical_map: PhysicalMapAggregate,
        current_tick: WorldTick,
    ) -> Set[WorldObjectId]:
        blocked_actor_ids: Set[WorldObjectId] = set()
        monsters_on_spot = self._monster_repository.find_by_spot_id(physical_map.spot_id)
        alive_monsters: List[MonsterAggregate] = []

        for monster in monsters_on_spot:
            if monster.coordinate is None:
                continue
            if monster.tick_hunger(current_tick):
                try:
                    monster.starve(current_tick)
                    self._monster_repository.save(monster)
                    self._unit_of_work.process_sync_events()
                except DomainException as exc:
                    self._logger.warning(
                        "Starvation skipped for actor %s: %s",
                        monster.world_object_id,
                        str(exc),
                    )
                blocked_actor_ids.add(monster.world_object_id)
                continue
            if monster.die_from_old_age(current_tick):
                try:
                    self._monster_repository.save(monster)
                    self._unit_of_work.process_sync_events()
                except DomainException as exc:
                    self._logger.warning(
                        "Old-age death skipped for actor %s: %s",
                        monster.world_object_id,
                        str(exc),
                    )
                blocked_actor_ids.add(monster.world_object_id)
                continue
            alive_monsters.append(monster)

        migrated_actor_id = self.apply_hunger_migration_for_spot(
            physical_map,
            current_tick,
            monsters_on_spot=alive_monsters,
        )
        if migrated_actor_id is not None:
            blocked_actor_ids.add(migrated_actor_id)

        return blocked_actor_ids

    def apply_hunger_migration_for_spot(
        self,
        physical_map: PhysicalMapAggregate,
        current_tick: WorldTick,
        monsters_on_spot: Optional[List[MonsterAggregate]] = None,
    ) -> Optional[WorldObjectId]:
        monsters = monsters_on_spot
        if monsters is None:
            monsters = self._monster_repository.find_by_spot_id(physical_map.spot_id)

        candidates: List[HungerMigrationCandidate] = []
        for monster in monsters:
            if monster.coordinate is None:
                continue
            candidates.append(
                HungerMigrationCandidate(
                    monster_id=monster.monster_id,
                    world_object_id=monster.world_object_id,
                    hunger=monster.hunger,
                    forage_threshold=monster.template.forage_threshold,
                    has_preferred_feed=bool(monster.template.preferred_feed_item_spec_ids),
                    spot_has_feed=self._spot_has_feed_for_monster(
                        physical_map,
                        monster,
                        current_tick,
                    ),
                )
            )

        selected_candidate = self._hunger_migration_policy.select_migrant(candidates)
        if selected_candidate is None:
            return None

        connected_spots_provider = self._connected_spots_provider_getter()
        map_transition_service = self._map_transition_service_getter()
        if connected_spots_provider is None or map_transition_service is None:
            return None

        migrant = self._monster_repository.find_by_world_object_id(
            selected_candidate.world_object_id
        )
        if migrant is None:
            return None

        connected = connected_spots_provider.get_connected_spots(physical_map.spot_id)
        if not connected:
            return None
        to_spot_id = random.choice(connected)
        gateways = physical_map.get_all_gateways()
        target_gateway = next(
            (gateway for gateway in gateways if gateway.target_spot_id == to_spot_id),
            None,
        )
        if target_gateway is None:
            return None
        to_map = self._physical_map_repository.find_by_spot_id(to_spot_id)
        if to_map is None:
            return None

        try:
            map_transition_service.transition_object(
                physical_map,
                to_map,
                migrant.world_object_id,
                target_gateway.landing_coordinate,
            )
            migrant.update_map_placement(to_spot_id, target_gateway.landing_coordinate)
            self._physical_map_repository.save(physical_map)
            self._physical_map_repository.save(to_map)
            self._monster_repository.save(migrant)
            self._unit_of_work.process_sync_events()
        except DomainException as exc:
            self._logger.warning(
                "Hunger migration skipped for monster %s: %s",
                migrant.monster_id,
                str(exc),
            )
            return None
        return migrant.world_object_id
