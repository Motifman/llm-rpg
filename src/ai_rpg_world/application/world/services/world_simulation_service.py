import logging
from typing import List, Callable, Any, Dict, Optional, Set, TYPE_CHECKING

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.weather_zone_repository import WeatherZoneRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxHitRecordedEvent,
    HitBoxMovedEvent,
    HitBoxObstacleCollidedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.enum.world_enum import BehaviorActionType
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.value_object.behavior_context import (
    SkillSelectionContext,
    TargetSelectionContext,
    GrowthContext,
)
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
    MonsterTemplateRepository,
)
from ai_rpg_world.domain.monster.repository.spawn_table_repository import SpawnTableRepository
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.spawn_slot import SpawnSlot
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import MonsterSkillExecutionDomainService
from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
from ai_rpg_world.domain.world.service.weather_effect_service import WeatherEffectService
from ai_rpg_world.domain.world.service.weather_config_service import WeatherConfigService
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
    DefaultWorldTimeConfigService,
)
from ai_rpg_world.domain.world.value_object.time_of_day import (
    TimeOfDay,
    time_of_day_from_tick,
    is_active_at_time,
)
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.combat.service.hit_box_config_service import (
    DefaultHitBoxConfigService,
    HitBoxConfigService,
)
from ai_rpg_world.domain.combat.service.hit_box_collision_service import HitBoxCollisionDomainService
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.world.aggro_store import AggroStore

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
        hit_box_config_service: Optional[HitBoxConfigService] = None,
        hit_box_collision_service: Optional[HitBoxCollisionDomainService] = None,
        aggro_store: Optional[AggroStore] = None,
        world_time_config_service: Optional[WorldTimeConfigService] = None,
        spawn_table_repository: Optional[SpawnTableRepository] = None,
        monster_template_repository: Optional[MonsterTemplateRepository] = None,
        monster_action_resolver_factory: Optional[
            Callable[[PhysicalMapAggregate, WorldObject], "IMonsterActionResolver"]
        ] = None,
    ):
        self._time_provider = time_provider
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
        self._hit_box_config_service = hit_box_config_service or DefaultHitBoxConfigService()
        self._hit_box_collision_service = hit_box_collision_service or HitBoxCollisionDomainService()
        self._unit_of_work = unit_of_work
        self._aggro_store = aggro_store
        self._world_time_config_service = world_time_config_service or DefaultWorldTimeConfigService()
        self._monster_action_resolver_factory = monster_action_resolver_factory
        self._logger = logging.getLogger(self.__class__.__name__)

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
            # deferされたsaveの影響でリポジトリから取得しても更新前の場合があるため、
            # 最新の状態を辞書で保持して同期に利用する
            latest_weather = self._update_weather_if_needed(current_tick)
            
            # 3. マップを順番に処理
            maps = self._physical_map_repository.find_all()
            
            # プレイヤーIDと所属マップの対応を保持（環境効果の一括適用のため）
            player_map_map: Dict[PlayerId, PhysicalMapAggregate] = {}
            
            for physical_map in maps:
                # 3.1 天候の同期
                self._sync_weather_to_map(physical_map, latest_weather)

                # 3.2 プレイヤーIDの収集
                for actor in physical_map.actors:
                    if actor.player_id:
                        player_map_map[actor.player_id] = physical_map

            # 3.3 環境効果の一括適用
            if player_map_map:
                self._apply_environmental_effects_bulk(player_map_map)

            # アクティブなスポット（プレイヤーが1人以上いるスポット）のみ行動更新・HitBox・save を行う
            active_spot_ids: Set[SpotId] = {pm.spot_id for pm in player_map_map.values()}

            # 3.5 スポーン・リスポーン判定（スロットベース or 従来のDEAD走査）
            ticks_per_day = self._world_time_config_service.get_ticks_per_day()
            time_of_day = time_of_day_from_tick(current_tick.value, ticks_per_day)
            if self._spawn_table_repository and self._monster_template_repository:
                self._process_spawn_and_respawn_by_slots(
                    active_spot_ids=active_spot_ids,
                    current_tick=current_tick,
                    time_of_day=time_of_day,
                )
            else:
                for monster in self._monster_repository.find_all():
                    if monster.status != MonsterStatusEnum.DEAD:
                        continue
                    if monster.spot_id is None or monster.spot_id not in active_spot_ids:
                        continue
                    if not monster.should_respawn(current_tick):
                        continue
                    condition = monster.template.respawn_info.condition
                    if condition is not None and not condition.is_satisfied_at(time_of_day):
                        continue
                    respawn_coord = monster.get_respawn_coordinate()
                    if respawn_coord is None:
                        continue
                    try:
                        monster.respawn(respawn_coord, current_tick, monster.spot_id)
                        self._monster_repository.save(monster)
                    except DomainException as e:
                        self._logger.warning(
                            "Respawn skipped for monster %s: %s",
                            monster.monster_id,
                            str(e),
                        )

            # 4. 各マップのアクターの行動更新（アクティブなスポットのみ；同一スポット内でプレイヤーとの距離が近い順に処理）
            for physical_map in maps:
                if physical_map.spot_id not in active_spot_ids:
                    continue
                for actor in self._actors_sorted_by_distance_to_players(physical_map):
                    # Busy状態のアクターはスキップ
                    if actor.is_busy(current_tick):
                        continue
                    # 活動時間帯でない自律アクターは行動しない（WAIT 相当）
                    if isinstance(actor.component, AutonomousBehaviorComponent):
                        ticks_per_day = self._world_time_config_service.get_ticks_per_day()
                        time_of_day = time_of_day_from_tick(current_tick.value, ticks_per_day)
                        if not is_active_at_time(actor.component.active_time, time_of_day):
                            continue
                        # Phase 6: 飢餓ティックと飢餓死判定
                        if actor.component.tick_hunger_and_starvation():
                            monster = self._monster_repository.find_by_world_object_id(actor.object_id)
                            if monster:
                                try:
                                    monster.starve(current_tick)
                                    self._monster_repository.save(monster)
                                    self._unit_of_work.process_sync_events()
                                except DomainException as e:
                                    self._logger.warning(
                                        "Starvation skipped for actor %s: %s",
                                        actor.object_id,
                                        str(e),
                                    )
                            continue
                        # 寿命判定（経過ティック ≥ max_age_ticks で NATURAL 死亡）
                        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
                        if monster and monster.die_from_old_age(current_tick):
                            try:
                                self._monster_repository.save(monster)
                                self._unit_of_work.process_sync_events()
                            except DomainException as e:
                                self._logger.warning(
                                    "Old-age death skipped for actor %s: %s",
                                    actor.object_id,
                                    str(e),
                                )
                            continue
                    try:
                        # 自律行動アクター用の skill_context / target_context / growth_context を組み立て
                        skill_context = self._build_skill_context_for_actor(actor, physical_map, current_tick)
                        target_context = self._build_target_context_for_actor(actor, physical_map, current_tick)
                        growth_context = self._build_growth_context_for_actor(actor, current_tick)

                        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
                        if monster and self._monster_action_resolver_factory is not None:
                            # モンスター: 観測を組み立て → Monster.decide → save → 実行
                            observation = self._behavior_service.build_observation(
                                actor.object_id,
                                physical_map,
                                target_context=target_context,
                                skill_context=skill_context,
                                growth_context=growth_context,
                                pack_rally_coordinate=None,
                                current_tick=current_tick,
                            )
                            resolver = self._monster_action_resolver_factory(
                                physical_map, actor
                            )
                            action = monster.decide(
                                observation,
                                current_tick,
                                actor.coordinate,
                                resolver,
                            )
                            self._monster_repository.save(monster)
                            self._unit_of_work.process_sync_events()
                        else:
                            # 非モンスター or ファクトリ未注入: 従来どおり plan_action
                            behavior_events: List = []
                            action = self._behavior_service.plan_action(
                                actor.object_id,
                                physical_map,
                                skill_context=skill_context,
                                target_context=target_context,
                                growth_context=growth_context,
                                current_tick=current_tick,
                                event_sink=behavior_events,
                            )
                            if monster:
                                for event in behavior_events:
                                    monster.add_event(event)
                                self._monster_repository.save(monster)
                                self._unit_of_work.process_sync_events()

                        if action.action_type == BehaviorActionType.MOVE:
                            # 移動実行
                            physical_map.move_object(actor.object_id, action.coordinate, current_tick)
                            # パトロール点到達時はモンスターの patrol_index を進める
                            if monster and self._monster_action_resolver_factory is not None:
                                if isinstance(actor.component, AutonomousBehaviorComponent):
                                    pts = actor.component.patrol_points
                                    if pts and action.coordinate == pts[monster.behavior_patrol_index]:
                                        monster.advance_patrol_index(len(pts))
                                        self._monster_repository.save(monster)
                        elif action.action_type == BehaviorActionType.USE_SKILL:
                            # USE_SKILL 時は skill_slot_index が必ず指定されていることを保証
                            if action.skill_slot_index is None:
                                raise ApplicationException(
                                    "USE_SKILL action must have skill_slot_index",
                                    action_type=BehaviorActionType.USE_SKILL,
                                )
                            self._execute_monster_skill_in_tick(
                                actor_id=actor.object_id,
                                physical_map=physical_map,
                                slot_index=action.skill_slot_index,
                                current_tick=current_tick,
                            )
                        # WAIT の場合は何もしない
                    except DomainException as e:
                        # ドメインルール違反（移動不可など）は警告ログにとどめる
                        self._logger.warning(
                            f"Behavior skipped for actor {actor.object_id} due to domain rule: {str(e)}"
                        )
                    except ApplicationException:
                        raise
                    except Exception as e:
                        # その他予期せぬエラー
                        self._logger.error(
                            f"Failed to update actor {actor.object_id} in map {physical_map.spot_id}: {str(e)}",
                            exc_info=True
                        )

                # 4.5 HitBoxの更新（移動・衝突判定）
                self._update_hit_boxes(physical_map, current_tick)
                
                # マップの状態を保存
                self._physical_map_repository.save(physical_map)
            
            return current_tick

    def _process_spawn_and_respawn_by_slots(
        self,
        active_spot_ids: Set[SpotId],
        current_tick: WorldTick,
        time_of_day: TimeOfDay,
    ) -> None:
        """スロット単位でスポーン・リスポーンを処理。条件を満たしたスロットに spawn または respawn する。"""
        for spot_id in active_spot_ids:
            table = self._spawn_table_repository.find_by_spot_id(spot_id)
            if not table:
                continue
            physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
            weather_type = (
                physical_map.weather_state.weather_type
                if physical_map and physical_map.weather_state
                else None
            )
            area_traits = getattr(physical_map, "area_traits", None) if physical_map else None
            monsters_for_spot = self._monster_repository.find_by_spot_id(spot_id)
            for slot in table.slots:
                if slot.condition is not None and not slot.condition.is_satisfied(
                    time_of_day, weather_type=weather_type, area_traits=area_traits
                ):
                    continue
                monster_for_slot = self._find_monster_for_slot(
                    slot, monsters_for_spot
                )
                count_alive = self._count_alive_for_slot(slot, monsters_for_spot)
                if count_alive >= slot.max_concurrent:
                    continue
                if monster_for_slot is not None:
                    if (
                        monster_for_slot.status == MonsterStatusEnum.DEAD
                        and monster_for_slot.should_respawn(current_tick)
                    ):
                        try:
                            monster_for_slot.respawn(
                                slot.coordinate, current_tick, slot.spot_id
                            )
                            self._monster_repository.save(monster_for_slot)
                            self._unit_of_work.process_sync_events()
                        except DomainException as e:
                            self._logger.warning(
                                "Respawn skipped for slot %s %s: %s",
                                slot.spot_id,
                                slot.coordinate,
                                str(e),
                            )
                else:
                    template = self._monster_template_repository.find_by_id(
                        slot.template_id
                    )
                    if not template:
                        continue
                    try:
                        monster_id = self._monster_repository.generate_monster_id()
                        world_object_id = (
                            self._monster_repository.generate_world_object_id_for_npc()
                        )
                        loadout = SkillLoadoutAggregate.create(
                            SkillLoadoutId(world_object_id.value),
                            world_object_id.value,
                            10,
                            10,
                        )
                        monster = MonsterAggregate.create(
                            monster_id,
                            template,
                            world_object_id,
                            skill_loadout=loadout,
                        )
                        monster.spawn(
                            slot.coordinate, slot.spot_id, current_tick
                        )
                        self._monster_repository.save(monster)
                        self._skill_loadout_repository.save(loadout)
                        self._unit_of_work.process_sync_events()
                    except DomainException as e:
                        self._logger.warning(
                            "Spawn skipped for slot %s %s: %s",
                            slot.spot_id,
                            slot.coordinate,
                            str(e),
                        )

    def _find_monster_for_slot(self, slot: SpawnSlot, monsters: List[MonsterAggregate]) -> Optional[MonsterAggregate]:
        """スロットに割り当てられたモンスターを1体返す（get_respawn_coordinate と template_id で一致）。"""
        for m in monsters:
            respawn_coord = m.get_respawn_coordinate()
            if (
                respawn_coord is not None
                and m.spot_id == slot.spot_id
                and respawn_coord == slot.coordinate
                and m.template.template_id == slot.template_id
            ):
                return m
        return None

    def _count_alive_for_slot(self, slot: SpawnSlot, monsters: List[MonsterAggregate]) -> int:
        """スロットに対応する ALIVE モンスター数を返す。"""
        return sum(
            1
            for m in monsters
            if m.status == MonsterStatusEnum.ALIVE
            and m.spot_id == slot.spot_id
            and m.get_respawn_coordinate() == slot.coordinate
            and m.template.template_id == slot.template_id
        )

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

    def _build_skill_context_for_actor(
        self,
        actor: WorldObject,
        physical_map: PhysicalMapAggregate,
        current_tick: WorldTick,
    ) -> Optional[SkillSelectionContext]:
        """
        自律行動のモンスターについて、使用可能スロットから SkillSelectionContext を組み立てる。
        モンスターでない、または取得失敗時は None を返す。
        """
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            return None
        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
        if not monster:
            return None
        loadout = monster.skill_loadout
        component = actor.component
        usable_slot_indices: set = set()
        for skill_info in component.available_skills:
            if loadout.can_use_skill(skill_info.slot_index, current_tick.value):
                usable_slot_indices.add(skill_info.slot_index)
        return SkillSelectionContext(usable_slot_indices=usable_slot_indices)

    def _build_growth_context_for_actor(
        self,
        actor: WorldObject,
        current_tick: WorldTick,
    ) -> Optional[GrowthContext]:
        """
        自律行動のモンスターについて、成長段階に応じた GrowthContext を組み立てる。
        growth_stages が無い場合は None（従来どおりコンポーネントの flee_threshold と CHASE 許可）。
        """
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            return None
        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
        if not monster or not monster.template.growth_stages:
            return None
        return GrowthContext(
            effective_flee_threshold=monster.get_effective_flee_threshold(current_tick),
            allow_chase=monster.get_allow_chase(current_tick),
        )

    def _build_target_context_for_actor(
        self,
        actor: WorldObject,
        physical_map: PhysicalMapAggregate,
        current_tick: WorldTick,
    ) -> Optional[TargetSelectionContext]:
        """
        自律行動のモンスターについて、ヘイト等から TargetSelectionContext を組み立てる。
        AggroMemoryPolicy があれば last_seen_tick からの経過で忘却したエントリは除外する。
        ヘイトストア未注入時や該当データなしの場合は None を返す。
        """
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            return None
        if self._aggro_store is None:
            return None
        component = actor.component
        policy = getattr(component, "aggro_memory_policy", None)
        threat_by_id = self._aggro_store.get_threat_by_attacker(
            physical_map.spot_id,
            actor.object_id,
            current_tick=current_tick.value,
            memory_policy=policy,
        )
        if not threat_by_id:
            return None
        return TargetSelectionContext(threat_by_id=threat_by_id)

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

    def _update_weather_if_needed(self, current_tick: WorldTick) -> Dict[SpotId, WeatherState]:
        """必要に応じて天候を更新する（設定された間隔ごと）
        
        Returns:
            Dict[SpotId, WeatherState]: 更新されたスポットIDと天候状態のマップ
        """
        latest_weather = {}
        interval = self._weather_config_service.get_update_interval_ticks()
        
        try:
            zones = self._weather_zone_repository.find_all()
            if not zones:
                self._logger.debug("No weather zones found")
                return latest_weather

            for zone in zones:
                if current_tick.value % interval == 0:
                    try:
                        new_state = WeatherSimulationService.simulate_next_weather(zone.current_state)
                        zone.change_weather(new_state)
                        self._weather_zone_repository.save(zone)
                        self._logger.info(f"Weather updated in zone {zone.zone_id} to {new_state.weather_type}")
                    except DomainException as e:
                        self._logger.error(f"Weather transition rule violation in zone {zone.zone_id}: {str(e)}")
                    except Exception as e:
                        self._logger.error(f"Unexpected error updating weather for zone {zone.zone_id}: {str(e)}", exc_info=True)
                
                # 最新の状態をスポットごとに保持
                for spot_id in zone.spot_ids:
                    latest_weather[spot_id] = zone.current_state
        except Exception as e:
            self._logger.error(f"Failed to retrieve weather zones: {str(e)}")
                
        return latest_weather

    def _sync_weather_to_map(self, physical_map: PhysicalMapAggregate, latest_weather: Dict[SpotId, WeatherState]) -> None:
        """天候ゾーンの状態を物理マップに同期する"""
        # まずは今回更新された（または保持されている）最新状態を確認
        if physical_map.spot_id in latest_weather:
            physical_map.set_weather(latest_weather[physical_map.spot_id])
            return

        # 辞書にない場合はリポジトリから取得
        try:
            zone = self._weather_zone_repository.find_by_spot_id(physical_map.spot_id)
            if zone:
                physical_map.set_weather(zone.current_state)
            else:
                # ゾーンが見つからない場合はデフォルト（晴れ）
                physical_map.set_weather(WeatherState.clear())
        except DomainException as e:
            self._logger.error(f"Domain error syncing weather to map {physical_map.spot_id}: {str(e)}")
            physical_map.set_weather(WeatherState.clear())
        except Exception as e:
            self._logger.error(f"Unexpected error syncing weather to map {physical_map.spot_id}: {str(e)}", exc_info=True)
            # エラー時もデフォルトに設定
            physical_map.set_weather(WeatherState.clear())

    def _apply_environmental_effects_bulk(self, player_map_map: Dict[PlayerId, PhysicalMapAggregate]) -> None:
        """アクター（プレイヤー）に対して環境効果（スタミナ減少など）を一括適用する"""
        player_ids = list(player_map_map.keys())
        try:
            player_statuses = self._player_status_repository.find_by_ids(player_ids)
            status_map = {s.player_id: s for s in player_statuses}
            
            updated_statuses = []
            
            for player_id, physical_map in player_map_map.items():
                player_status = status_map.get(player_id)
                if not player_status:
                    self._logger.warning(f"Player status not found for player {player_id}")
                    continue
                
                if not player_status.can_act():
                    continue

                # スタミナ減少量の計算
                drain = WeatherEffectService.calculate_environmental_stamina_drain(
                    physical_map.weather_state,
                    physical_map.environment_type
                )

                if drain > 0:
                    if player_status.stamina.value > 0:
                        actual_drain = min(player_status.stamina.value, drain)
                        try:
                            player_status.consume_stamina(actual_drain)
                            updated_statuses.append(player_status)
                        except DomainException as e:
                            # スタミナ不足などはここで処理（実際にはminで防いでいるが、念のため）
                            self._logger.warning(f"Could not apply environmental effect to player {player_id}: {str(e)}")
                        except Exception as e:
                            self._logger.error(f"Unexpected error consuming stamina for player {player_id}: {str(e)}", exc_info=True)
            
            if updated_statuses:
                # 一括保存
                self._player_status_repository.save_all(updated_statuses)
                    
        except Exception as e:
            self._logger.error(f"Error applying environmental effects in bulk: {str(e)}", exc_info=True)

    def _update_hit_boxes(self, physical_map: PhysicalMapAggregate, current_tick: WorldTick) -> None:
        """
        指定マップ上のHitBoxを更新し、衝突判定を行う。
        - 移動・寿命更新は HitBoxAggregate.on_tick に委譲
        - 障害物・オブジェクト衝突判定はアプリケーション層で調停
        """
        try:
            hit_boxes = self._hit_box_repository.find_active_by_spot_id(physical_map.spot_id)
        except Exception as e:
            self._logger.error(
                f"Failed to load hit boxes for map {physical_map.spot_id}: {str(e)}",
                exc_info=True,
            )
            return

        total_substeps_executed = 0
        total_collision_checks = 0
        guard_trigger_count = 0

        for hit_box in hit_boxes:
            try:
                substeps_per_tick = self._hit_box_config_service.get_substeps_for_hit_box(hit_box)
                max_collision_checks = self._hit_box_config_service.get_max_collision_checks_per_tick()
                collision_checks_for_hit_box = 0
                guard_triggered = False
                step_ratio = 1.0 / substeps_per_tick
                for _ in range(substeps_per_tick):
                    if not hit_box.is_active:
                        break
                    
                    # 有効化タイミングに達していない場合はスキップ（移動も判定も行わない）
                    if not hit_box.is_activated(current_tick):
                        break

                    total_substeps_executed += 1
                    hit_box.on_tick(current_tick, step_ratio=step_ratio)

                    if hit_box.is_active:
                        used_checks, guard_triggered = self._hit_box_collision_service.resolve_collisions(
                            physical_map,
                            hit_box,
                            max_collision_checks=max_collision_checks - collision_checks_for_hit_box,
                        )
                        collision_checks_for_hit_box += used_checks
                        if guard_triggered:
                            guard_trigger_count += 1
                            self._logger.warning(
                                f"Collision check guard triggered for hit box {hit_box.hit_box_id} "
                                f"in map {physical_map.spot_id}. limit={max_collision_checks}"
                            )
                            break

                self._hit_box_repository.save(hit_box)
                total_collision_checks += collision_checks_for_hit_box
            except DomainException as e:
                self._logger.warning(
                    f"HitBox update skipped for {hit_box.hit_box_id} due to domain rule: {str(e)}"
                )
            except Exception as e:
                self._logger.error(
                    f"Failed to update hit box {hit_box.hit_box_id} in map {physical_map.spot_id}: {str(e)}",
                    exc_info=True,
                )

        self._logger.debug(
            f"HitBox update stats map={physical_map.spot_id} hit_boxes={len(hit_boxes)} "
            f"substeps={total_substeps_executed} collision_checks={total_collision_checks} "
            f"guard_triggers={guard_trigger_count}"
        )

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
