from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.world.services.caching_pathfinding_service import (
    CachingPathfindingService,
)
from ai_rpg_world.application.world.services.world_simulation_service import (
    WorldSimulationApplicationService,
)
from ai_rpg_world.domain.combat.service.hit_box_collision_service import (
    HitBoxCollisionDomainService,
)
from ai_rpg_world.domain.combat.service.hit_box_config_service import (
    DefaultHitBoxConfigService,
)
from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import (
    MonsterSkillExecutionDomainService,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import (
    StatGrowthFactor,
)
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
    SkillLoadoutAggregate,
)
from ai_rpg_world.domain.skill.service.skill_execution_service import (
    SkillExecutionDomainService,
)
from ai_rpg_world.domain.skill.service.skill_targeting_service import (
    SkillTargetingDomainService,
)
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import (
    SkillToHitBoxDomainService,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
    PhysicalMapAggregate,
)
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.weather_config_service import (
    DefaultWeatherConfigService,
)
from ai_rpg_world.domain.world.service.world_time_config_service import (
    DefaultWorldTimeConfigService,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_hit_box_repository import (
    InMemoryHitBoxRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_weather_zone_repository import (
    InMemoryWeatherZoneRepository,
)
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class _InMemorySkillLoadoutRepo:
    def __init__(self) -> None:
        self._data: dict[Any, Any] = {}

    def save(self, loadout: SkillLoadoutAggregate) -> None:
        self._data[loadout.loadout_id] = loadout

    def find_by_id(self, loadout_id: Any) -> SkillLoadoutAggregate | None:
        return self._data.get(loadout_id)


@dataclass
class WorldSimulationTestBed:
    service: WorldSimulationApplicationService
    time_provider: InMemoryGameTimeProvider
    repository: InMemoryPhysicalMapRepository
    weather_zone_repo: InMemoryWeatherZoneRepository
    player_status_repo: InMemoryPlayerStatusRepository
    hit_box_repo: InMemoryHitBoxRepository
    unit_of_work: InMemoryUnitOfWork
    event_publisher: Any
    monster_repo: InMemoryMonsterAggregateRepository
    skill_loadout_repo: _InMemorySkillLoadoutRepo


def build_world_simulation_test_bed() -> WorldSimulationTestBed:
    data_store = InMemoryDataStore()
    data_store.clear_all()

    time_provider = InMemoryGameTimeProvider(initial_tick=10)

    def create_uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

    unit_of_work, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
        unit_of_work_factory=create_uow,
        data_store=data_store,
    )

    repository = InMemoryPhysicalMapRepository(data_store, unit_of_work)
    weather_zone_repo = InMemoryWeatherZoneRepository(data_store, unit_of_work)
    player_status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
    hit_box_repo = InMemoryHitBoxRepository(data_store, unit_of_work)
    monster_repo = InMemoryMonsterAggregateRepository(data_store, unit_of_work)

    from ai_rpg_world.application.world.handlers.monster_decided_to_interact_handler import (
        MonsterDecidedToInteractHandler,
    )
    from ai_rpg_world.application.world.handlers.monster_decided_to_move_handler import (
        MonsterDecidedToMoveHandler,
    )
    from ai_rpg_world.application.world.handlers.monster_decided_to_use_skill_handler import (
        MonsterDecidedToUseSkillHandler,
    )
    from ai_rpg_world.application.world.handlers.monster_fed_handler import (
        MonsterFedHandler,
    )
    from ai_rpg_world.application.world.services.monster_action_resolver import (
        create_monster_action_resolver_factory,
    )
    from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
    from ai_rpg_world.domain.world.service.skill_selection_policy import (
        FirstInRangeSkillPolicy,
    )
    from ai_rpg_world.infrastructure.events.monster_event_handler_registry import (
        MonsterEventHandlerRegistry,
    )
    from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import (
        AStarPathfindingStrategy,
    )

    pathfinding_service = PathfindingService(AStarPathfindingStrategy())
    caching_pathfinding = CachingPathfindingService(
        pathfinding_service,
        time_provider=time_provider,
        ttl_ticks=5,
    )
    behavior_service = BehaviorService()
    weather_config = DefaultWeatherConfigService(update_interval_ticks=1)
    hit_box_config = DefaultHitBoxConfigService(substeps_per_tick=4)
    hit_box_collision_service = HitBoxCollisionDomainService()
    skill_loadout_repo = _InMemorySkillLoadoutRepo()
    skill_execution_service = SkillExecutionDomainService(
        SkillTargetingDomainService(),
        SkillToHitBoxDomainService(),
    )
    monster_skill_execution_domain_service = MonsterSkillExecutionDomainService(
        skill_execution_service
    )
    hit_box_factory = HitBoxFactory()
    monster_action_resolver_factory = create_monster_action_resolver_factory(
        caching_pathfinding,
        FirstInRangeSkillPolicy(),
    )
    monster_decided_to_move_handler = MonsterDecidedToMoveHandler(
        physical_map_repository=repository,
        monster_repository=monster_repo,
    )
    monster_decided_to_use_skill_handler = MonsterDecidedToUseSkillHandler(
        physical_map_repository=repository,
        monster_repository=monster_repo,
        monster_skill_execution_domain_service=monster_skill_execution_domain_service,
        hit_box_factory=hit_box_factory,
        hit_box_repository=hit_box_repo,
        skill_loadout_repository=skill_loadout_repo,
    )
    monster_decided_to_interact_handler = MonsterDecidedToInteractHandler(
        physical_map_repository=repository,
    )
    monster_fed_handler = MonsterFedHandler(monster_repository=monster_repo)
    MonsterEventHandlerRegistry(
        monster_decided_to_move_handler,
        monster_decided_to_use_skill_handler,
        monster_decided_to_interact_handler,
        monster_fed_handler,
    ).register_handlers(event_publisher)

    service = WorldSimulationApplicationService(
        time_provider=time_provider,
        physical_map_repository=repository,
        weather_zone_repository=weather_zone_repo,
        player_status_repository=player_status_repo,
        hit_box_repository=hit_box_repo,
        behavior_service=behavior_service,
        weather_config_service=weather_config,
        unit_of_work=unit_of_work,
        monster_repository=monster_repo,
        skill_loadout_repository=skill_loadout_repo,
        monster_skill_execution_domain_service=monster_skill_execution_domain_service,
        hit_box_factory=hit_box_factory,
        hit_box_config_service=hit_box_config,
        hit_box_collision_service=hit_box_collision_service,
        world_time_config_service=DefaultWorldTimeConfigService(ticks_per_day=24),
        monster_action_resolver_factory=monster_action_resolver_factory,
    )

    return WorldSimulationTestBed(
        service=service,
        time_provider=time_provider,
        repository=repository,
        weather_zone_repo=weather_zone_repo,
        player_status_repo=player_status_repo,
        hit_box_repo=hit_box_repo,
        unit_of_work=unit_of_work,
        event_publisher=event_publisher,
        monster_repo=monster_repo,
        skill_loadout_repo=skill_loadout_repo,
    )


def create_player_status(
    player_id: int = 1,
    *,
    current_spot_id: int = 1,
) -> PlayerStatusAggregate:
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=ExpTable(100, 1.5),
        growth=Growth(1, 0, ExpTable(100, 1.5)),
        gold=Gold(0),
        hp=Hp.create(100, 100),
        mp=Mp.create(30, 30),
        stamina=Stamina.create(100, 100),
        current_spot_id=SpotId(current_spot_id),
        current_coordinate=Coordinate(0, 0, 0),
    )


def create_player_actor(
    player_id: int = 1,
    *,
    coordinate: Coordinate | None = None,
    busy_until: Any = None,
) -> WorldObject:
    return WorldObject(
        WorldObjectId(player_id),
        coordinate or Coordinate(0, 0, 0),
        ObjectTypeEnum.PLAYER,
        component=ActorComponent(
            direction=DirectionEnum.EAST,
            player_id=PlayerId(player_id),
        ),
        busy_until=busy_until,
    )


def create_autonomous_actor(
    object_id: int = 200,
    *,
    coordinate: Coordinate | None = None,
) -> WorldObject:
    return WorldObject(
        WorldObjectId(object_id),
        coordinate or Coordinate(1, 0, 0),
        ObjectTypeEnum.NPC,
        component=AutonomousBehaviorComponent(race="goblin", vision_range=5, fov_angle=360),
    )


def create_physical_map(
    spot_id: int,
    *,
    objects: list[WorldObject] | None = None,
    size: int = 3,
) -> PhysicalMapAggregate:
    return PhysicalMapAggregate.create(
        SpotId(spot_id),
        [
            Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(size)
            for y in range(size)
        ],
        objects=objects or [],
    )
