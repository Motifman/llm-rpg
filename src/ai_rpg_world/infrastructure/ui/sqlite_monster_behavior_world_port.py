"""SQLite-backed monster behavior simulation for the web demo runtime."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from threading import RLock
from typing import Union

from ai_rpg_world.application.ui.handlers.ui_event_handler import UiEventHandler
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.ui.services.game_scene_projection_bootstrap_service import (
    GameSceneBootstrapConfig,
    GameSceneProjectionBootstrapService,
)
from ai_rpg_world.application.world.services.caching_pathfinding_service import (
    CachingPathfindingService,
)
from ai_rpg_world.application.world.services.monster_action_resolver import (
    create_monster_action_resolver_factory,
)
from ai_rpg_world.application.world.services.monster_behavior_context_builder import (
    MonsterBehaviorContextBuilder,
)
from ai_rpg_world.application.world.services.monster_feed_query_service import (
    MonsterFeedQueryService,
)
from ai_rpg_world.application.world.services.monster_foraging_rule import (
    MonsterForagingRule,
)
from ai_rpg_world.application.world.services.monster_pursuit_failure_rule import (
    MonsterPursuitFailureRule,
)
from ai_rpg_world.application.world.services.monster_target_context_builder import (
    MonsterTargetContextBuilder,
)
from ai_rpg_world.application.world.services.monster_behavior_coordinator import (
    MonsterBehaviorCoordinator,
)
from ai_rpg_world.application.world.services.world_simulation_monster_behavior_stage_service import (
    WorldSimulationMonsterBehaviorStageService,
)
from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    attach_world_state_sqlite_repositories,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    BehaviorStateTransitionService,
)
from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import (
    MonsterSkillExecutionDomainService,
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
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.skill_selection_policy import (
    FirstInRangeSkillPolicy,
)
from ai_rpg_world.domain.world.service.world_time_config_service import (
    DefaultWorldTimeConfigService,
)
from ai_rpg_world.infrastructure.events.event_handler_composition import (
    EventHandlerComposition,
)
from ai_rpg_world.infrastructure.events.event_handler_profile import EventHandlerProfile
from ai_rpg_world.infrastructure.events.monster_event_handler_registry import (
    MonsterEventHandlerRegistry,
)
from ai_rpg_world.infrastructure.events.ui_event_handler_registry import (
    UiEventHandlerRegistry,
)
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.infrastructure.ui.in_memory_game_scene_event_broker import (
    InMemoryGameSceneEventBroker,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_transactional_scope_factory import (
    create_sqlite_scope_with_event_publisher,
)
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import (
    AStarPathfindingStrategy,
)
from ai_rpg_world.application.static_master_sqlite_wiring import (
    attach_static_master_sqlite_repositories,
)
from ai_rpg_world.application.skill.skill_sqlite_wiring import (
    attach_skill_sqlite_repositories,
)
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


class SqliteMonsterBehaviorWorldPort:
    """Run domain monster behavior against the SQLite demo world on each tick."""

    def __init__(
        self,
        *,
        database: Union[str, Path],
        projection: GameSceneProjection,
        broker: InMemoryGameSceneEventBroker,
        bootstrap_config: GameSceneBootstrapConfig,
        time_provider: InMemoryGameTimeProvider,
        db_lock: RLock | None = None,
    ) -> None:
        self._database = str(Path(database).expanduser().resolve())
        self._projection = projection
        self._broker = broker
        self._bootstrap_config = bootstrap_config
        self._time_provider = time_provider
        self._db_lock = db_lock
        self._logger = logging.getLogger(self.__class__.__name__)

    def advance_tick(self, current_tick: int) -> None:
        lock = self._db_lock or nullcontext()
        with lock:
            connection = sqlite3.connect(
                self._database,
                timeout=5.0,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            try:
                scope, event_publisher = create_sqlite_scope_with_event_publisher(
                    connection=connection
                )
                world_state = attach_world_state_sqlite_repositories(
                    connection,
                    event_sink=scope,
                )
                static_master = attach_static_master_sqlite_repositories(connection)
                skill_repositories = attach_skill_sqlite_repositories(connection)

                ui_handler = UiEventHandler(
                    self._projection,
                    self._broker,
                    physical_map_repository=world_state.world_runtime.physical_maps,
                )
                ui_registry = UiEventHandlerRegistry(ui_handler)
                EventHandlerComposition(ui_registry=ui_registry).register_for_profile(
                    event_publisher,
                    EventHandlerProfile.FULL,
                )

                monster_move_handler = MonsterDecidedToMoveHandler(
                    physical_map_repository=world_state.world_runtime.physical_maps,
                    monster_repository=world_state.world_runtime.monsters,
                )
                monster_skill_execution_domain_service = MonsterSkillExecutionDomainService(
                    SkillExecutionDomainService(
                        SkillTargetingDomainService(),
                        SkillToHitBoxDomainService(),
                    )
                )
                MonsterEventHandlerRegistry(
                    monster_move_handler,
                    MonsterDecidedToUseSkillHandler(
                        physical_map_repository=world_state.world_runtime.physical_maps,
                        monster_repository=world_state.world_runtime.monsters,
                        monster_skill_execution_domain_service=monster_skill_execution_domain_service,
                        hit_box_factory=HitBoxFactory(),
                        hit_box_repository=world_state.world_runtime.hit_boxes,
                        skill_loadout_repository=skill_repositories.runtime.loadouts,
                    ),
                    MonsterDecidedToInteractHandler(
                        physical_map_repository=world_state.world_runtime.physical_maps,
                    ),
                    MonsterFedHandler(
                        monster_repository=world_state.world_runtime.monsters,
                    ),
                ).register_handlers(event_publisher)

                behavior_stage = WorldSimulationMonsterBehaviorStageService(
                    world_time_config_service=DefaultWorldTimeConfigService(ticks_per_day=24),
                    logger=self._logger,
                    actors_sorted_by_distance_to_players=self._actors_sorted_by_distance_to_players,
                    behavior_coordinator=MonsterBehaviorCoordinator(
                        monster_repository=world_state.world_runtime.monsters,
                        behavior_service=BehaviorService(),
                        transition_service=BehaviorStateTransitionService(),
                        action_resolver_factory=create_monster_action_resolver_factory(
                            CachingPathfindingService(
                                PathfindingService(AStarPathfindingStrategy()),
                                time_provider=self._time_provider,
                                ttl_ticks=5,
                            ),
                            FirstInRangeSkillPolicy(),
                        ),
                        foraging_rule=MonsterForagingRule(
                            MonsterFeedQueryService(static_master.readers.loot_tables)
                        ),
                        pursuit_failure_rule=MonsterPursuitFailureRule(),
                        unit_of_work=scope,
                        behavior_context_builder=MonsterBehaviorContextBuilder(
                            world_state.world_runtime.monsters
                        ),
                        target_context_builder=MonsterTargetContextBuilder(
                            monster_repository=world_state.world_runtime.monsters,
                        ),
                        sync_event_dispatcher=scope.sync_event_dispatcher,
                    ),
                )

                maps = world_state.world_runtime.physical_maps.find_all()
                active_spot_ids = {
                    physical_map.spot_id
                    for physical_map in maps
                    if any(actor.player_id is not None for actor in physical_map.actors)
                }
                if not active_spot_ids:
                    return

                with scope:
                    behavior_stage.run(
                        maps,
                        active_spot_ids,
                        WorldTick(current_tick),
                        skipped_actor_ids=set(),
                    )

                bootstrap_service = GameSceneProjectionBootstrapService(
                    spot_repository=world_state.world_structure.spots,
                    physical_map_repository=world_state.world_runtime.physical_maps,
                    player_profile_repository=world_state.player_state.player_profiles,
                    config=self._bootstrap_config,
                )
                for snapshot in bootstrap_service.build_initial_snapshots():
                    self._projection.synchronize_snapshot(snapshot)
            except Exception:
                self._logger.exception(
                    "Monster behavior simulation tick failed",
                    extra={"current_tick": current_tick},
                )
            finally:
                connection.close()

    @staticmethod
    def _actors_sorted_by_distance_to_players(physical_map) -> list:
        actors = physical_map.actors
        player_coords = [
            actor.coordinate for actor in actors if actor.player_id is not None
        ]
        if not player_coords:
            return actors
        return sorted(
            actors,
            key=lambda actor: min(
                actor.coordinate.distance_to(player_coordinate)
                for player_coordinate in player_coords
            ),
        )


__all__ = ["SqliteMonsterBehaviorWorldPort"]
