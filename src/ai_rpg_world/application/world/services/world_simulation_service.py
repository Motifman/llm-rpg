import logging
from typing import List, Callable, Any, Dict, Optional, Set, TYPE_CHECKING

from ai_rpg_world.application.llm.contracts.interfaces import (
    ILlmTurnTrigger,
    IReflectionRunner,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.weather_zone_repository import WeatherZoneRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
    MonsterTemplateRepository,
)
from ai_rpg_world.domain.monster.repository.spawn_table_repository import SpawnTableRepository
from ai_rpg_world.domain.item.repository.loot_table_repository import LootTableRepository
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository
from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import MonsterSkillExecutionDomainService
from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
from ai_rpg_world.domain.world.service.weather_config_service import WeatherConfigService
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.combat.service.hit_box_config_service import (
    HitBoxConfigService,
)
from ai_rpg_world.domain.combat.service.hit_box_collision_service import HitBoxCollisionDomainService
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.world.aggro_store import AggroStore
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.application.world.services.pursuit_continuation_service import (
    PursuitContinuationService,
)
from ai_rpg_world.application.world.services.world_simulation_collaborator_factory import (
    WorldSimulationCollaboratorFactory,
    WorldSimulationDefaultDependencies,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.action_resolver import IMonsterActionResolver


class WorldSimulationApplicationService:
    """ワールド全体の進行・シミュレーションを管理するアプリケーションサービス"""

    def __init__(
        self,
        time_provider: GameTimeProvider,
        physical_map_repository: PhysicalMapRepository,
        weather_zone_repository: WeatherZoneRepository,
        player_status_repository: PlayerStatusRepository,
        hit_box_repository: HitBoxRepository,
        behavior_service: BehaviorService,
        weather_config_service: WeatherConfigService,
        unit_of_work: UnitOfWork,
        monster_repository: MonsterRepository,
        skill_loadout_repository: SkillLoadoutRepository,
        monster_skill_execution_domain_service: MonsterSkillExecutionDomainService,
        hit_box_factory: HitBoxFactory,
        monster_action_resolver_factory: Callable[
            [PhysicalMapAggregate, WorldObject], "IMonsterActionResolver"
        ],
        hit_box_config_service: Optional[HitBoxConfigService] = None,
        hit_box_collision_service: Optional[HitBoxCollisionDomainService] = None,
        aggro_store: Optional[AggroStore] = None,
        world_time_config_service: Optional[WorldTimeConfigService] = None,
        spawn_table_repository: Optional[SpawnTableRepository] = None,
        monster_template_repository: Optional[MonsterTemplateRepository] = None,
        loot_table_repository: Optional[LootTableRepository] = None,
        connected_spots_provider: Optional[IConnectedSpotsProvider] = None,
        map_transition_service: Optional[MapTransitionService] = None,
        llm_turn_trigger: Optional[ILlmTurnTrigger] = None,
        reflection_runner: Optional[IReflectionRunner] = None,
        movement_service: Optional[Any] = None,
        pursuit_continuation_service: Optional[PursuitContinuationService] = None,
        harvest_command_service: Optional[Any] = None,
    ):
        self._time_provider = time_provider
        self._llm_turn_trigger = llm_turn_trigger
        self._reflection_runner = reflection_runner
        self._loot_table_repository = loot_table_repository
        self._connected_spots_provider = connected_spots_provider
        self._map_transition_service = map_transition_service
        self._physical_map_repository = physical_map_repository
        self._weather_zone_repository = weather_zone_repository
        self._player_status_repository = player_status_repository
        self._hit_box_repository = hit_box_repository
        self._behavior_service = behavior_service
        self._weather_config_service = weather_config_service
        self._monster_repository = monster_repository
        self._skill_loadout_repository = skill_loadout_repository
        self._spawn_table_repository = spawn_table_repository
        self._monster_template_repository = monster_template_repository
        self._monster_skill_execution_domain_service = monster_skill_execution_domain_service
        self._hit_box_factory = hit_box_factory
        self._unit_of_work = unit_of_work
        self._aggro_store = aggro_store
        self._monster_action_resolver_factory = monster_action_resolver_factory
        self._movement_service = movement_service
        self._pursuit_continuation_service = pursuit_continuation_service
        self._harvest_command_service = harvest_command_service
        self._logger = logging.getLogger(self.__class__.__name__)
        defaults = WorldSimulationDefaultDependencies.resolve(
            hit_box_config_service=hit_box_config_service,
            hit_box_collision_service=hit_box_collision_service,
            world_time_config_service=world_time_config_service,
        )
        self._hit_box_config_service = defaults.hit_box_config_service
        self._hit_box_collision_service = defaults.hit_box_collision_service
        self._world_time_config_service = defaults.world_time_config_service

        collaborators = WorldSimulationCollaboratorFactory(
            physical_map_repository=self._physical_map_repository,
            weather_zone_repository=self._weather_zone_repository,
            player_status_repository=self._player_status_repository,
            hit_box_repository=self._hit_box_repository,
            behavior_service=self._behavior_service,
            weather_config_service=self._weather_config_service,
            unit_of_work=self._unit_of_work,
            monster_repository=self._monster_repository,
            skill_loadout_repository=self._skill_loadout_repository,
            monster_action_resolver_factory=self._monster_action_resolver_factory,
            monster_action_resolver_factory_getter=lambda: self._monster_action_resolver_factory,
            defaults=defaults,
            logger=self._logger,
            aggro_store=self._aggro_store,
            aggro_store_getter=lambda: self._aggro_store,
            spawn_table_repository=self._spawn_table_repository,
            monster_template_repository=self._monster_template_repository,
            loot_table_repository=self._loot_table_repository,
            connected_spots_provider=self._connected_spots_provider,
            map_transition_service=self._map_transition_service,
            movement_service=self._movement_service,
            pursuit_continuation_service=self._pursuit_continuation_service,
            harvest_command_service=self._harvest_command_service,
            actors_sorted_by_distance_to_players=self._actors_sorted_by_distance_to_players,
        ).build()

        self._hunger_migration_policy = collaborators.hunger_migration_policy
        self._monster_feed_query_service = collaborators.monster_feed_query_service
        self._monster_behavior_context_builder = collaborators.monster_behavior_context_builder
        self._monster_target_context_builder = collaborators.monster_target_context_builder
        self._monster_foraging_rule = collaborators.monster_foraging_rule
        self._monster_pursuit_failure_rule = collaborators.monster_pursuit_failure_rule
        self._monster_spawn_slot_service = collaborators.monster_spawn_slot_service
        self._environment_effect_service = collaborators.environment_effect_service
        self._hit_box_updater = collaborators.hit_box_updater
        self._monster_lifecycle_survival_coordinator = (
            collaborators.monster_lifecycle_survival_coordinator
        )
        self._monster_behavior_coordinator = collaborators.monster_behavior_coordinator
        self._environment_stage = collaborators.environment_stage
        self._movement_stage = collaborators.movement_stage
        self._harvest_stage = collaborators.harvest_stage
        self._monster_lifecycle_stage = collaborators.monster_lifecycle_stage
        self._monster_behavior_stage = collaborators.monster_behavior_stage
        self._hit_box_stage = collaborators.hit_box_stage
        self._environment_stage._weather_config_service_getter = (
            lambda: self._weather_config_service
        )
        self._movement_stage._movement_service_getter = lambda: self._movement_service
        self._movement_stage._pursuit_continuation_service_getter = (
            lambda: self._pursuit_continuation_service
        )
        self._harvest_stage._harvest_command_service_getter = (
            lambda: self._harvest_command_service
        )
        self._hit_box_updater._hit_box_config_service_getter = (
            lambda: self._hit_box_config_service
        )
        self._hit_box_updater._hit_box_collision_service_getter = (
            lambda: self._hit_box_collision_service
        )

    def tick(self) -> WorldTick:
        """1ティック進め、世界の全ての要素を更新する"""
        return self._execute_with_error_handling(
            operation=lambda: self._tick_impl(),
            context={"action": "tick"}
        )

    def _tick_impl(self) -> WorldTick:
        with self._unit_of_work:
            # 1. ティックを進める
            current_tick = self._time_provider.advance_tick()
            
            # 2. 天候の更新（長周期）
            maps = self._physical_map_repository.find_all()
            self._environment_stage.run(current_tick, maps)

            # プレイヤーIDと所属マップの対応を保持（環境効果の一括適用のため）
            player_map_map: Dict[PlayerId, PhysicalMapAggregate] = {}

            # 3.1.5 プレイヤーの継続移動を進める
            if self._movement_service is not None:
                self._movement_stage.run(current_tick)
                maps = self._physical_map_repository.find_all()

            if self._harvest_command_service is not None:
                self._harvest_stage.run(maps, current_tick)
                maps = self._physical_map_repository.find_all()

            # 3.2 プレイヤーIDの収集
            for physical_map in maps:
                for actor in physical_map.actors:
                    if actor.player_id:
                        player_map_map[actor.player_id] = physical_map

            # 3.3 環境効果の一括適用
            if player_map_map:
                self._environment_effect_service.apply_bulk(player_map_map)

            # アクティブなスポット（プレイヤーが1人以上いるスポット）のみ行動更新・HitBox・save を行う
            active_spot_ids: Set[SpotId] = {pm.spot_id for pm in player_map_map.values()}

            blocked_actor_ids = self._monster_lifecycle_stage.run(
                maps,
                active_spot_ids,
                current_tick,
            )
            self._monster_behavior_stage.run(
                maps,
                active_spot_ids,
                current_tick,
                skipped_actor_ids=blocked_actor_ids,
            )
            self._hit_box_stage.run(maps, active_spot_ids, current_tick)

        self._run_post_tick_hooks(current_tick)
        return current_tick

    def _run_post_tick_hooks(self, current_tick: WorldTick) -> None:
        if self._llm_turn_trigger is not None:
            self._llm_turn_trigger.run_scheduled_turns()
        if self._reflection_runner is not None:
            self._reflection_runner.run_after_tick(current_tick)

    def _actors_sorted_by_distance_to_players(
        self, physical_map: PhysicalMapAggregate
    ) -> List[WorldObject]:
        """
        同一マップ上のプレイヤー位置との距離が近い順にアクターを返す。
        プレイヤーが誰もいない場合は physical_map.actors の順のまま返す。
        距離は同一スポット内の座標（Coordinate.distance_to）で計算する。
        """
        actors = physical_map.actors
        player_coords = [
            a.coordinate for a in actors
            if a.player_id is not None
        ]
        if not player_coords:
            return list(actors)
        return sorted(
            actors,
            key=lambda a: min(
                a.coordinate.distance_to(p) for p in player_coords
            ),
        )

    def _execute_monster_skill_in_tick(
        self,
        actor_id: WorldObjectId,
        physical_map: PhysicalMapAggregate,
        slot_index: int,
        current_tick: WorldTick,
    ) -> None:
        """
        tick 内で自律アクター（モンスター）のスキル使用を実行する。
        同一 UoW 内でドメインサービスを呼び、HitBox 生成・集約の保存まで行う。
        モンスター未検出やドメインルール違反時はログのみでスキップする。
        """
        monster = self._monster_repository.find_by_world_object_id(actor_id)
        if not monster:
            self._logger.warning(
                f"Monster not found for world_object_id={actor_id}, skipping USE_SKILL"
            )
            return

        loadout = monster.skill_loadout
        try:
            spawn_params = self._monster_skill_execution_domain_service.execute(
                monster=monster,
                loadout=loadout,
                physical_map=physical_map,
                slot_index=slot_index,
                current_tick=current_tick,
            )
        except DomainException as e:
            self._logger.warning(
                f"Monster skill skipped for actor {actor_id} due to domain rule: {str(e)}"
            )
            return

        skill_spec = loadout.get_current_deck(current_tick.value).get_skill(slot_index)
        skill_id = str(skill_spec.skill_id) if skill_spec else None
        hit_box_ids = self._hit_box_repository.batch_generate_ids(len(spawn_params))
        hit_boxes = self._hit_box_factory.create_from_params(
            hit_box_ids=hit_box_ids,
            params=spawn_params,
            spot_id=physical_map.spot_id,
            owner_id=actor_id,
            start_tick=current_tick,
            skill_id=skill_id,
        )
        if hit_boxes:
            self._hit_box_repository.save_all(hit_boxes)
        self._monster_repository.save(monster)
        self._skill_loadout_repository.save(loadout)

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        try:
            return operation()
        except ApplicationException as e:
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise ApplicationException(str(e), cause=e, **context)
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)
