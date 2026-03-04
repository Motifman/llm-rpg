import logging
from typing import Optional, List, Dict, Tuple, Callable, Any
from datetime import datetime

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.repository.transition_policy_repository import ITransitionPolicyRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
    TransitionContext,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.service.global_pathfinding_service import GlobalPathfindingService
from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
from ai_rpg_world.domain.world.service.weather_effect_service import WeatherEffectService
from ai_rpg_world.domain.world.service.movement_config_service import MovementConfigService
from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent
from ai_rpg_world.domain.world.exception.map_exception import (
    ObjectNotFoundException, TileNotFoundException, InvalidMovementException, ActorBusyException as DomainActorBusyException
)
from ai_rpg_world.domain.player.exception import PlayerDownedException
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.application.world.contracts.commands import (
    CancelMovementCommand,
    MoveTileCommand,
    SetDestinationCommand,
    TickMovementCommand,
)
from ai_rpg_world.application.world.contracts.dtos import MoveResultDto
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException, WorldSystemErrorException
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    MovementCommandException,
    PlayerNotFoundException,
    MapNotFoundException,
    MovementInvalidException,
    PlayerStaminaExhaustedException,
    PathBlockedException,
    ActorBusyException,
    MapTransitionInvalidException
)


class MovementApplicationService:
    """移動に関するユースケースを統合するアプリケーションサービス"""
    
    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: PhysicalMapRepository,
        spot_repository: SpotRepository,
        connected_spots_provider: IConnectedSpotsProvider,
        global_pathfinding_service: GlobalPathfindingService,
        movement_config_service: MovementConfigService,
        time_provider: GameTimeProvider,
        unit_of_work: UnitOfWork,
        transition_policy_repository: Optional[ITransitionPolicyRepository] = None,
        transition_condition_evaluator: Optional[TransitionConditionEvaluator] = None,
    ):
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
        self._spot_repository = spot_repository
        self._connected_spots_provider = connected_spots_provider
        self._global_pathfinding_service = global_pathfinding_service
        self._movement_config_service = movement_config_service
        self._time_provider = time_provider
        self._unit_of_work = unit_of_work
        self._transition_policy_repository = transition_policy_repository
        self._transition_condition_evaluator = transition_condition_evaluator
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except WorldApplicationException as e:
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise MovementCommandException(str(e), player_id=context.get('player_id'))
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise WorldSystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                         original_exception=e)

    def move_tile(self, command: MoveTileCommand) -> MoveResultDto:
        """タイルベースの移動（人間プレイヤー用）"""
        return self._execute_with_error_handling(
            operation=lambda: self._move_tile_impl(command),
            context={
                "action": "move_tile",
                "player_id": command.player_id,
                "direction": command.direction
            }
        )

    def _move_tile_impl(self, command: MoveTileCommand) -> MoveResultDto:
        with self._unit_of_work:
            return self._execute_movement_step(command.player_id, direction=command.direction)

    def set_destination(self, command: SetDestinationCommand) -> MoveResultDto:
        """目的地を設定する（LLMエージェントまたは自動移動用）。スポットまたはロケーション指定で座標不要。"""
        return self._execute_with_error_handling(
            operation=lambda: self._set_destination_impl(command),
            context={
                "action": "set_destination",
                "player_id": command.player_id,
                "target_spot_id": command.target_spot_id,
            }
        )

    def _set_destination_impl(self, command: SetDestinationCommand) -> MoveResultDto:
        player_id = PlayerId(command.player_id)
        target_spot_id = SpotId(command.target_spot_id)

        with self._unit_of_work:
            player_status = self._player_status_repository.find_by_id(player_id)
            if not player_status:
                raise PlayerNotFoundException(command.player_id)

            current_spot_id = player_status.current_spot_id
            current_coord = player_status.current_coordinate

            if not current_spot_id or not current_coord:
                raise MovementInvalidException("Player is not placed on any map", command.player_id)

            # 目標座標の決定（destination_type に応じて）
            if command.destination_type == "location":
                target_physical_map = self._physical_map_repository.find_by_spot_id(target_spot_id)
                if not target_physical_map:
                    raise MapNotFoundException(int(target_spot_id))
                location_area_id = LocationAreaId(command.target_location_area_id)
                try:
                    location_area = target_physical_map.get_location_area(location_area_id)
                except Exception:
                    raise MovementInvalidException(
                        f"Location area {command.target_location_area_id} not found in spot {command.target_spot_id}",
                        command.player_id,
                    )
                target_coord = location_area.get_reference_coordinate()
            else:
                # spot のときは経路計算で別スポットなら target_coord は未使用。同スポットなら既に到着。
                target_coord = current_coord  # 同スポット判定用のダミー

            # 既に目的地にいる場合は経路を設定しない
            if current_spot_id == target_spot_id:
                if command.destination_type == "spot":
                    return self._create_success_dto(
                        player_status,
                        current_spot_id,
                        current_coord,
                        current_coord,
                        self._time_provider.get_current_tick().value,
                        "既に目的地のスポットにいます",
                    )
                # location: 既に同スポットにいるので、ロケーション内にいるか確認（location_area は上で取得済み）
                if location_area.contains(current_coord):
                    return self._create_success_dto(
                        player_status,
                        current_spot_id,
                        current_coord,
                        current_coord,
                        self._time_provider.get_current_tick().value,
                        "既に目的地のロケーションにいます",
                    )
                # 同スポットだがロケーション内にいない場合は target_coord は既に設定済みで経路計算へ

            physical_map = self._physical_map_repository.find_by_spot_id(current_spot_id)
            if not physical_map:
                raise MapNotFoundException(int(current_spot_id))

            world_object_id = WorldObjectId.create(int(player_id))
            try:
                actor = physical_map.get_actor(world_object_id)
            except ObjectNotFoundException:
                raise MovementInvalidException("Player object not found in map", command.player_id)

            temp_goal, path = self._global_pathfinding_service.calculate_global_path(
                current_spot_id=current_spot_id,
                current_coord=current_coord,
                target_spot_id=target_spot_id,
                target_coord=target_coord,
                physical_map=physical_map,
                connected_spots_provider=self._connected_spots_provider,
                world_object_id=world_object_id,
                capability=actor.capability or MovementCapability.normal_walk(),
            )

            if not path or temp_goal is None:
                return self._create_failure_dto(command.player_id, "目的地への経路が見つかりません", player_status)

            goal_location_area_id = (
                LocationAreaId(command.target_location_area_id)
                if command.destination_type == "location" and command.target_location_area_id
                else None
            )
            player_status.set_destination(
                temp_goal,
                path,
                goal_destination_type=command.destination_type,
                goal_spot_id=target_spot_id,
                goal_location_area_id=goal_location_area_id,
            )
            self._player_status_repository.save(player_status)

            return self._create_success_dto(
                player_status,
                current_spot_id,
                current_coord,
                current_coord,
                self._time_provider.get_current_tick().value,
                "目的地を設定しました",
            )

    def tick_movement(self, command: TickMovementCommand) -> MoveResultDto:
        """集約に保存されたパスに基づいて1ステップ進む"""
        return self._execute_with_error_handling(
            operation=lambda: self._tick_movement_impl(command),
            context={
                "action": "tick_movement",
                "player_id": command.player_id
            }
        )

    def cancel_movement(self, command: CancelMovementCommand) -> MoveResultDto:
        """経路をキャンセルする（割り込み時など）。目的地設定を解除する。"""
        return self._execute_with_error_handling(
            operation=lambda: self._cancel_movement_impl(command),
            context={"action": "cancel_movement", "player_id": command.player_id},
        )

    def _cancel_movement_impl(self, command: CancelMovementCommand) -> MoveResultDto:
        """経路をクリアする。キャンセル自体は成功するが、現在地が取得できない場合は失敗 DTO を返す（成功 DTO を組み立てられないため）。"""
        player_id = PlayerId(command.player_id)
        with self._unit_of_work:
            player_status = self._player_status_repository.find_by_id(player_id)
            if not player_status:
                raise PlayerNotFoundException(command.player_id)
            player_status.clear_path()
            self._player_status_repository.save(player_status)
            if not player_status.current_spot_id or not player_status.current_coordinate:
                return self._create_failure_dto(command.player_id, "現在地が不明です", player_status)
            coord = player_status.current_coordinate
            return self._create_success_dto(
                player_status,
                player_status.current_spot_id,
                coord,
                coord,
                0,
                "移動を中断しました。",
            )

    def _tick_movement_impl(self, command: TickMovementCommand) -> MoveResultDto:
        player_id = PlayerId(command.player_id)
        
        with self._unit_of_work:
            player_status = self._player_status_repository.find_by_id(player_id)
            if not player_status:
                raise PlayerNotFoundException(command.player_id)

            next_coord = player_status.advance_path()
            if not next_coord:
                return self._create_failure_dto(command.player_id, "移動計画がないか、既に到着しています", player_status)
            
            # 移動実行
            try:
                result = self._execute_movement_step(
                    command.player_id, target_coordinate=next_coord, player_status=player_status
                )
                if not result.success:
                    player_status.clear_path()
                    self._player_status_repository.save(player_status)
                    return result

                # 到着判定（スポット到着 or ロケーション到着）
                player_status = self._player_status_repository.find_by_id(player_id)
                if player_status.goal_spot_id and player_status.current_spot_id == player_status.goal_spot_id:
                    if player_status.goal_destination_type == "spot":
                        player_status.clear_path()
                        self._player_status_repository.save(player_status)
                    elif player_status.goal_destination_type == "location" and player_status.goal_location_area_id:
                        physical_map = self._physical_map_repository.find_by_spot_id(player_status.current_spot_id)
                        if physical_map and player_status.current_coordinate:
                            try:
                                loc_area = physical_map.get_location_area(player_status.goal_location_area_id)
                                if loc_area.contains(player_status.current_coordinate):
                                    player_status.clear_path()
                                    self._player_status_repository.save(player_status)
                            except Exception:
                                pass

                return result
            except (MovementInvalidException, PathBlockedException, ActorBusyException, PlayerStaminaExhaustedException) as e:
                # 業務的な失敗の場合は、経路をクリアした状態を保存して正常終了（失敗DTO）を返す
                player_status.clear_path()
                self._player_status_repository.save(player_status)
                return self._create_failure_dto(command.player_id, str(e), player_status)

    def _execute_movement_step(
        self, 
        player_id_int: int, 
        direction: Optional[DirectionEnum] = None, 
        target_coordinate: Optional[Coordinate] = None,
        player_status: Optional[PlayerStatusAggregate] = None
    ) -> MoveResultDto:
        """移動の1ステップを実行する"""
        player_id = PlayerId(player_id_int)
        current_tick = self._time_provider.get_current_tick()
        
        if not player_status:
            player_status = self._player_status_repository.find_by_id(player_id)
            if not player_status:
                raise PlayerNotFoundException(player_id_int)
        
        # 1. 基本状態チェック（戦闘不能など）
        if not player_status.can_act():
            return self._create_failure_dto(player_id_int, "現在行動できません", player_status)

        current_spot_id = player_status.current_spot_id
        if not current_spot_id:
            raise MovementInvalidException("Player is not on any map", player_id_int)
        
        # 2. 物理マップとアクターの取得
        physical_map = self._physical_map_repository.find_by_spot_id(current_spot_id)
        if not physical_map:
            raise MapNotFoundException(int(current_spot_id))
            
        world_object_id = WorldObjectId.create(player_id_int)
        try:
            actor = physical_map.get_actor(world_object_id)
        except ObjectNotFoundException:
            raise MovementInvalidException("Player object not found in physical map", player_id_int)

        # 3. 移動先座標の決定
        from_coord = actor.coordinate
        if direction:
            to_coord = from_coord.neighbor(direction)
        elif target_coordinate:
            to_coord = target_coordinate
        else:
            raise MovementInvalidException("No movement target specified", player_id_int)

        # 3.5 ゲートウェイ遷移条件の評価（該当ゲートウェイがある場合のみ）
        transition_result = self._evaluate_gateway_transition_conditions(
            physical_map, to_coord, current_spot_id, player_id_int, player_status
        )
        if transition_result is not None:
            allowed, failure_message = transition_result
            if not allowed:
                return self._create_failure_dto(
                    player_id_int,
                    failure_message or "この出口は通過できません",
                    player_status,
                )

        # 4. スタミナ消費の計算とチェック
        try:
            stamina_cost = self._compute_stamina_cost_for_move(physical_map, to_coord)
            if player_status.stamina.value < stamina_cost:
                raise PlayerStaminaExhaustedException(player_id_int, stamina_cost, player_status.stamina.value)
            
            # 5. ドメインロジックの実行（物理マップ内移動）
            physical_map.move_object(world_object_id, to_coord, current_tick, actor.capability)
            
            # スタミナ消費
            player_status.consume_stamina(int(stamina_cost))
            
            # プレイヤー状態の更新（座標）
            player_status.update_location(current_spot_id, to_coord)
            
            # 6. イベント収集と後処理
            # ゲートウェイ判定などは同期イベントハンドラに委譲される
            message = "移動しました"
            if any(isinstance(e, GatewayTriggeredEvent) for e in physical_map.get_events()):
                 message = "マップを移動しました"

            # 保存
            self._physical_map_repository.save(physical_map)
            self._player_status_repository.save(player_status)
            
            # 同期イベントの即時実行（マップ遷移などを反映させるため）
            self._unit_of_work.process_sync_events()
            
            # 状態が変わっている可能性があるため再ロード
            player_status = self._player_status_repository.find_by_id(player_id)
            
            return self._create_success_dto(player_status, current_spot_id, from_coord, player_status.current_coordinate, actor.busy_until.value, message)

        except DomainActorBusyException as e:
            raise ActorBusyException(player_id_int, int(actor.busy_until.value - current_tick.value))
        except (TileNotFoundException, InvalidMovementException) as e:
            raise PathBlockedException(player_id_int, {"x": to_coord.x, "y": to_coord.y, "z": to_coord.z})

    def _evaluate_gateway_transition_conditions(
        self,
        physical_map: PhysicalMapAggregate,
        to_coord: Coordinate,
        current_spot_id: SpotId,
        player_id_int: int,
        player_status: PlayerStatusAggregate,
    ) -> Optional[Tuple[bool, Optional[str]]]:
        """
        移動先がゲートウェイに含まれる場合、遷移条件を評価する。
        該当ゲートウェイがなければ None、条件がなければ (True, None)、
        条件ありなら (allowed, failure_message) を返す。
        """
        if not self._transition_policy_repository or not self._transition_condition_evaluator:
            return None
        for gateway in physical_map.get_all_gateways():
            if gateway.contains(to_coord):
                conditions = self._transition_policy_repository.get_conditions(
                    current_spot_id, gateway.target_spot_id
                )
                if conditions:
                    context = TransitionContext(
                        player_id=player_id_int,
                        player_status=player_status,
                        from_spot_id=current_spot_id,
                        to_spot_id=gateway.target_spot_id,
                        current_weather=physical_map.weather_state,
                    )
                    return self._transition_condition_evaluator.evaluate(conditions, context)
                break
        return None

    def _compute_stamina_cost_for_move(
        self, physical_map: PhysicalMapAggregate, to_coord: Coordinate
    ) -> float:
        """移動先タイルのスタミナコスト（天候倍率込み）を計算する。"""
        tile = physical_map.get_tile(to_coord)
        base_stamina_cost = self._movement_config_service.get_stamina_cost(tile.terrain_type)
        weather_multiplier = WeatherEffectService.calculate_stamina_multiplier(
            physical_map.weather_state,
            physical_map.environment_type,
        )
        return base_stamina_cost * weather_multiplier

    def _create_success_dto(self, player_status, from_spot_id, from_coord, to_coord, arrival_tick, message) -> MoveResultDto:
        # 名前情報の取得
        profile = self._player_profile_repository.find_by_id(player_status.player_id)
        if not profile:
            raise PlayerNotFoundException(int(player_status.player_id))
        player_name = profile.name.value
            
        # スポット名の取得（SpotRepositoryを使用）
        from_spot = self._spot_repository.find_by_id(from_spot_id)
        if not from_spot:
            raise MapNotFoundException(int(from_spot_id))
        from_spot_name = from_spot.name

        to_spot = self._spot_repository.find_by_id(player_status.current_spot_id)
        if not to_spot:
            raise MapNotFoundException(int(player_status.current_spot_id))
        to_spot_name = to_spot.name

        return MoveResultDto(
            success=True,
            player_id=int(player_status.player_id),
            player_name=player_name,
            from_spot_id=int(from_spot_id),
            from_spot_name=from_spot_name,
            to_spot_id=int(player_status.current_spot_id),
            to_spot_name=to_spot_name,
            from_coordinate={"x": from_coord.x, "y": from_coord.y, "z": from_coord.z},
            to_coordinate={"x": to_coord.x, "y": to_coord.y, "z": to_coord.z},
            moved_at=datetime.now(),
            busy_until_tick=arrival_tick,
            message=message
        )

    def _create_failure_dto(self, player_id_int: int, message: str, player_status: Optional[PlayerStatusAggregate] = None) -> MoveResultDto:
        player_id = PlayerId(player_id_int)
        player_name = ""
        from_spot_id = 0
        from_spot_name = ""
        to_spot_id = 0
        to_spot_name = ""
        from_coord_dict = {"x": 0, "y": 0, "z": 0}
        to_coord_dict = {"x": 0, "y": 0, "z": 0}

        if player_status:
            profile = self._player_profile_repository.find_by_id(player_id)
            if profile:
                player_name = profile.name.value
            
            if player_status.current_spot_id:
                from_spot_id = int(player_status.current_spot_id)
                to_spot_id = from_spot_id
                spot = self._spot_repository.find_by_id(player_status.current_spot_id)
                if spot:
                    from_spot_name = spot.name
                    to_spot_name = spot.name
            
            if player_status.current_coordinate:
                c = player_status.current_coordinate
                from_coord_dict = {"x": c.x, "y": c.y, "z": c.z}
                to_coord_dict = from_coord_dict

        return MoveResultDto(
            success=False,
            player_id=player_id_int,
            player_name=player_name,
            from_spot_id=from_spot_id,
            from_spot_name=from_spot_name,
            to_spot_id=to_spot_id,
            to_spot_name=to_spot_name,
            from_coordinate=from_coord_dict,
            to_coordinate=to_coord_dict,
            moved_at=datetime.now(),
            busy_until_tick=0,
            message="移動失敗",
            error_message=message
        )
