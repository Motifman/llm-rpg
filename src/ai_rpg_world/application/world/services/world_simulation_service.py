import logging
from typing import List, Callable, Any, Dict, Optional

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
from ai_rpg_world.domain.world.value_object.behavior_context import SkillSelectionContext, TargetSelectionContext
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository
from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import MonsterSkillExecutionDomainService
from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
from ai_rpg_world.domain.world.service.weather_effect_service import WeatherEffectService
from ai_rpg_world.domain.world.service.weather_config_service import WeatherConfigService
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
        self._monster_skill_execution_domain_service = monster_skill_execution_domain_service
        self._hit_box_factory = hit_box_factory
        self._hit_box_config_service = hit_box_config_service or DefaultHitBoxConfigService()
        self._hit_box_collision_service = hit_box_collision_service or HitBoxCollisionDomainService()
        self._unit_of_work = unit_of_work
        self._aggro_store = aggro_store
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
            
            # 4. 各マップのアクターの行動更新
            for physical_map in maps:
                for actor in physical_map.actors:
                    # Busy状態のアクターはスキップ
                    if actor.is_busy(current_tick):
                        continue
                    
                    try:
                        # 自律行動アクター用の skill_context / target_context を組み立て（モンスターでない場合は None）
                        skill_context = self._build_skill_context_for_actor(actor, physical_map, current_tick)
                        target_context = self._build_target_context_for_actor(actor, physical_map)
                        # 自律行動アクターの計画
                        action = self._behavior_service.plan_action(
                            actor.object_id,
                            physical_map,
                            skill_context=skill_context,
                            target_context=target_context,
                        )
                        
                        if action.action_type == BehaviorActionType.MOVE:
                            # 移動実行
                            physical_map.move_object(actor.object_id, action.coordinate, current_tick)
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

    def _build_target_context_for_actor(
        self,
        actor: WorldObject,
        physical_map: PhysicalMapAggregate,
    ) -> Optional[TargetSelectionContext]:
        """
        自律行動のモンスターについて、ヘイト等から TargetSelectionContext を組み立てる。
        ヘイトストア未注入時や該当データなしの場合は None を返す。
        """
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            return None
        if self._aggro_store is None:
            return None
        threat_by_id = self._aggro_store.get_threat_by_attacker(
            physical_map.spot_id, actor.object_id
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
