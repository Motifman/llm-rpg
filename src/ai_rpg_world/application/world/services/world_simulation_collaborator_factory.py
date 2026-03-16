import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ai_rpg_world.application.world.aggro_store import AggroStore
from ai_rpg_world.application.world.services.hunger_migration_policy import (
    HungerMigrationPolicy,
)
from ai_rpg_world.application.world.services.monster_behavior_context_builder import (
    MonsterBehaviorContextBuilder,
)
from ai_rpg_world.application.world.services.monster_behavior_coordinator import (
    MonsterBehaviorCoordinator,
)
from ai_rpg_world.application.world.services.monster_feed_query_service import (
    MonsterFeedQueryService,
)
from ai_rpg_world.application.world.services.monster_foraging_rule import (
    MonsterForagingRule,
)
from ai_rpg_world.application.world.services.monster_lifecycle_survival_coordinator import (
    MonsterLifecycleSurvivalCoordinator,
)
from ai_rpg_world.application.world.services.monster_pursuit_failure_rule import (
    MonsterPursuitFailureRule,
)
from ai_rpg_world.application.world.services.monster_spawn_slot_service import (
    MonsterSpawnSlotService,
)
from ai_rpg_world.application.world.services.monster_target_context_builder import (
    MonsterTargetContextBuilder,
)
from ai_rpg_world.application.world.services.pursuit_continuation_service import (
    PursuitContinuationService,
)
from ai_rpg_world.application.world.services.world_simulation_environment_effect_service import (
    WorldSimulationEnvironmentEffectService,
)
from ai_rpg_world.application.world.services.world_simulation_environment_stage_service import (
    WorldSimulationEnvironmentStageService,
)
from ai_rpg_world.application.world.services.world_simulation_harvest_stage_service import (
    WorldSimulationHarvestStageService,
)
from ai_rpg_world.application.world.services.world_simulation_hit_box_stage_service import (
    WorldSimulationHitBoxStageService,
)
from ai_rpg_world.application.world.services.world_simulation_hit_box_updater import (
    WorldSimulationHitBoxUpdater,
)
from ai_rpg_world.application.world.services.world_simulation_monster_behavior_stage_service import (
    WorldSimulationMonsterBehaviorStageService,
)
from ai_rpg_world.application.world.services.world_simulation_monster_lifecycle_stage_service import (
    WorldSimulationMonsterLifecycleStageService,
)
from ai_rpg_world.application.world.services.world_simulation_movement_stage_service import (
    WorldSimulationMovementStageService,
)
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.combat.service.hit_box_collision_service import (
    HitBoxCollisionDomainService,
)
from ai_rpg_world.domain.combat.service.hit_box_config_service import (
    DefaultHitBoxConfigService,
    HitBoxConfigService,
)
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.item.repository.loot_table_repository import LootTableRepository
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
    MonsterTemplateRepository,
)
from ai_rpg_world.domain.monster.repository.spawn_table_repository import SpawnTableRepository
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    BehaviorStateTransitionService,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.repository.connected_spots_provider import (
    IConnectedSpotsProvider,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.repository.weather_zone_repository import WeatherZoneRepository
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.domain.world.service.weather_config_service import WeatherConfigService
from ai_rpg_world.domain.world.service.world_time_config_service import (
    DefaultWorldTimeConfigService,
    WorldTimeConfigService,
)


@dataclass(frozen=True)
class WorldSimulationDefaultDependencies:
    hit_box_config_service: HitBoxConfigService
    hit_box_collision_service: HitBoxCollisionDomainService
    world_time_config_service: WorldTimeConfigService

    @classmethod
    def resolve(
        cls,
        *,
        hit_box_config_service: HitBoxConfigService | None,
        hit_box_collision_service: HitBoxCollisionDomainService | None,
        world_time_config_service: WorldTimeConfigService | None,
    ) -> "WorldSimulationDefaultDependencies":
        return cls(
            hit_box_config_service=hit_box_config_service or DefaultHitBoxConfigService(),
            hit_box_collision_service=(
                hit_box_collision_service or HitBoxCollisionDomainService()
            ),
            world_time_config_service=(
                world_time_config_service or DefaultWorldTimeConfigService()
            ),
        )


@dataclass(frozen=True)
class WorldSimulationCollaborators:
    hunger_migration_policy: HungerMigrationPolicy
    monster_feed_query_service: MonsterFeedQueryService
    monster_behavior_context_builder: MonsterBehaviorContextBuilder
    monster_target_context_builder: MonsterTargetContextBuilder
    monster_foraging_rule: MonsterForagingRule
    monster_pursuit_failure_rule: MonsterPursuitFailureRule
    monster_spawn_slot_service: MonsterSpawnSlotService
    environment_effect_service: WorldSimulationEnvironmentEffectService
    hit_box_updater: WorldSimulationHitBoxUpdater
    monster_lifecycle_survival_coordinator: MonsterLifecycleSurvivalCoordinator
    monster_behavior_coordinator: MonsterBehaviorCoordinator
    environment_stage: WorldSimulationEnvironmentStageService
    movement_stage: WorldSimulationMovementStageService
    harvest_stage: WorldSimulationHarvestStageService
    monster_lifecycle_stage: WorldSimulationMonsterLifecycleStageService
    monster_behavior_stage: WorldSimulationMonsterBehaviorStageService
    hit_box_stage: WorldSimulationHitBoxStageService


class WorldSimulationCollaboratorFactory:
    """world simulation facade が使う collaborator 群を構成する。"""

    def __init__(
        self,
        *,
        physical_map_repository: PhysicalMapRepository,
        weather_zone_repository: WeatherZoneRepository,
        player_status_repository: PlayerStatusRepository,
        hit_box_repository: HitBoxRepository,
        behavior_service: BehaviorService,
        weather_config_service: WeatherConfigService,
        unit_of_work: UnitOfWork,
        monster_repository: MonsterRepository,
        skill_loadout_repository: SkillLoadoutRepository,
        monster_action_resolver_factory: Callable[[PhysicalMapAggregate, WorldObject], Any],
        monster_action_resolver_factory_getter: Callable[
            [], Callable[[PhysicalMapAggregate, WorldObject], Any]
        ] | None,
        defaults: WorldSimulationDefaultDependencies,
        logger: logging.Logger,
        aggro_store: AggroStore | None,
        aggro_store_getter: Callable[[], AggroStore | None] | None,
        spawn_table_repository: SpawnTableRepository | None,
        monster_template_repository: MonsterTemplateRepository | None,
        loot_table_repository: LootTableRepository | None,
        connected_spots_provider: IConnectedSpotsProvider | None,
        map_transition_service: MapTransitionService | None,
        movement_service: Any | None,
        pursuit_continuation_service: PursuitContinuationService | None,
        harvest_command_service: Any | None,
        actors_sorted_by_distance_to_players: Callable[[PhysicalMapAggregate], list[WorldObject]],
    ) -> None:
        self._physical_map_repository = physical_map_repository
        self._weather_zone_repository = weather_zone_repository
        self._player_status_repository = player_status_repository
        self._hit_box_repository = hit_box_repository
        self._behavior_service = behavior_service
        self._weather_config_service = weather_config_service
        self._unit_of_work = unit_of_work
        self._monster_repository = monster_repository
        self._skill_loadout_repository = skill_loadout_repository
        self._monster_action_resolver_factory = monster_action_resolver_factory
        self._monster_action_resolver_factory_getter = (
            monster_action_resolver_factory_getter
        )
        self._defaults = defaults
        self._logger = logger
        self._aggro_store = aggro_store
        self._aggro_store_getter = aggro_store_getter
        self._spawn_table_repository = spawn_table_repository
        self._monster_template_repository = monster_template_repository
        self._loot_table_repository = loot_table_repository
        self._connected_spots_provider = connected_spots_provider
        self._map_transition_service = map_transition_service
        self._movement_service = movement_service
        self._pursuit_continuation_service = pursuit_continuation_service
        self._harvest_command_service = harvest_command_service
        self._actors_sorted_by_distance_to_players = actors_sorted_by_distance_to_players

    def build(self) -> WorldSimulationCollaborators:
        sync_event_dispatcher = getattr(
            self._unit_of_work, "sync_event_dispatcher", None
        )
        hunger_migration_policy = HungerMigrationPolicy()
        monster_feed_query_service = MonsterFeedQueryService(self._loot_table_repository)
        monster_behavior_context_builder = MonsterBehaviorContextBuilder(
            self._monster_repository
        )
        monster_target_context_builder = MonsterTargetContextBuilder(
            monster_repository=self._monster_repository,
            aggro_store=self._aggro_store,
            aggro_store_getter=self._aggro_store_getter,
        )
        monster_foraging_rule = MonsterForagingRule(monster_feed_query_service)
        monster_pursuit_failure_rule = MonsterPursuitFailureRule()
        monster_spawn_slot_service = MonsterSpawnSlotService(
            physical_map_repository=self._physical_map_repository,
            monster_repository=self._monster_repository,
            skill_loadout_repository=self._skill_loadout_repository,
            spawn_table_repository=self._spawn_table_repository,
            monster_template_repository=self._monster_template_repository,
            unit_of_work=self._unit_of_work,
            logger=self._logger,
            sync_event_dispatcher=sync_event_dispatcher,
        )
        environment_effect_service = WorldSimulationEnvironmentEffectService(
            player_status_repository=self._player_status_repository,
            logger=self._logger,
        )
        hit_box_updater = WorldSimulationHitBoxUpdater(
            hit_box_repository=self._hit_box_repository,
            hit_box_config_service=self._defaults.hit_box_config_service,
            hit_box_collision_service=self._defaults.hit_box_collision_service,
            logger=self._logger,
            hit_box_config_service_getter=lambda: self._defaults.hit_box_config_service,
            hit_box_collision_service_getter=lambda: self._defaults.hit_box_collision_service,
        )
        monster_lifecycle_survival_coordinator = MonsterLifecycleSurvivalCoordinator(
            monster_repository=self._monster_repository,
            physical_map_repository=self._physical_map_repository,
            connected_spots_provider_getter=lambda: self._connected_spots_provider,
            map_transition_service_getter=lambda: self._map_transition_service,
            hunger_migration_policy=hunger_migration_policy,
            spot_has_feed_for_monster=monster_feed_query_service.spot_has_feed_for_monster,
            unit_of_work=self._unit_of_work,
            logger=self._logger,
            sync_event_dispatcher=sync_event_dispatcher,
        )
        monster_behavior_coordinator = MonsterBehaviorCoordinator(
            monster_repository=self._monster_repository,
            behavior_service=self._behavior_service,
            transition_service=BehaviorStateTransitionService(),
            action_resolver_factory=self._monster_action_resolver_factory,
            action_resolver_factory_getter=self._monster_action_resolver_factory_getter,
            foraging_rule=monster_foraging_rule,
            pursuit_failure_rule=monster_pursuit_failure_rule,
            unit_of_work=self._unit_of_work,
            behavior_context_builder=monster_behavior_context_builder,
            target_context_builder=monster_target_context_builder,
            sync_event_dispatcher=sync_event_dispatcher,
        )
        environment_stage = WorldSimulationEnvironmentStageService(
            weather_zone_repository=self._weather_zone_repository,
            weather_config_service=self._weather_config_service,
            logger=self._logger,
            weather_config_service_getter=lambda: self._weather_config_service,
        )
        movement_stage = WorldSimulationMovementStageService(
            player_status_repository=self._player_status_repository,
            physical_map_repository=self._physical_map_repository,
            movement_service_getter=lambda: self._movement_service,
            pursuit_continuation_service_getter=lambda: self._pursuit_continuation_service,
        )
        harvest_stage = WorldSimulationHarvestStageService(
            harvest_command_service_getter=lambda: self._harvest_command_service,
            logger=self._logger,
        )
        monster_lifecycle_stage = WorldSimulationMonsterLifecycleStageService(
            world_time_config_service=self._defaults.world_time_config_service,
            has_spawn_slot_support=lambda: (
                self._spawn_table_repository is not None
                and self._monster_template_repository is not None
            ),
            has_hunger_migration_support=lambda: (
                self._connected_spots_provider is not None
                and self._map_transition_service is not None
                and self._loot_table_repository is not None
            ),
            process_spawn_and_respawn_by_slots=(
                monster_spawn_slot_service.process_spawn_and_respawn_by_slots
            ),
            process_respawn_legacy=monster_spawn_slot_service.process_respawn_legacy,
            survival_coordinator=monster_lifecycle_survival_coordinator,
        )
        monster_behavior_stage = WorldSimulationMonsterBehaviorStageService(
            world_time_config_service=self._defaults.world_time_config_service,
            logger=self._logger,
            actors_sorted_by_distance_to_players=self._actors_sorted_by_distance_to_players,
            behavior_coordinator=monster_behavior_coordinator,
        )
        hit_box_stage = WorldSimulationHitBoxStageService(
            physical_map_repository=self._physical_map_repository,
            update_hit_boxes=hit_box_updater.update_hit_boxes,
        )
        return WorldSimulationCollaborators(
            hunger_migration_policy=hunger_migration_policy,
            monster_feed_query_service=monster_feed_query_service,
            monster_behavior_context_builder=monster_behavior_context_builder,
            monster_target_context_builder=monster_target_context_builder,
            monster_foraging_rule=monster_foraging_rule,
            monster_pursuit_failure_rule=monster_pursuit_failure_rule,
            monster_spawn_slot_service=monster_spawn_slot_service,
            environment_effect_service=environment_effect_service,
            hit_box_updater=hit_box_updater,
            monster_lifecycle_survival_coordinator=monster_lifecycle_survival_coordinator,
            monster_behavior_coordinator=monster_behavior_coordinator,
            environment_stage=environment_stage,
            movement_stage=movement_stage,
            harvest_stage=harvest_stage,
            monster_lifecycle_stage=monster_lifecycle_stage,
            monster_behavior_stage=monster_behavior_stage,
            hit_box_stage=hit_box_stage,
        )
