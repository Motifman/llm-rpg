import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple, Callable, Any, Literal
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
from ai_rpg_world.domain.world.service.passable_adjacent_finder import PassableAdjacentFinder
from ai_rpg_world.domain.world.service.arrival_policy import ArrivalPolicy, ArrivalCheckResult
from ai_rpg_world.application.world.services.move_result_assembler import MoveResultAssembler
from ai_rpg_world.application.world.services.set_destination_service import (
    SetDestinationService,
    SetDestinationResult,
    ReplanPathCalculationResult,
)
from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent
from ai_rpg_world.domain.world.exception.map_exception import (
    ObjectNotFoundException,
    TileNotFoundException,
    InvalidMovementException,
    ActorBusyException as DomainActorBusyException,
    CoordinateValidationException,
    InvalidPathRequestException,
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

@dataclass(frozen=True)
class MovementReplanResult:
    """Narrow result for runtime path replanning without executing movement."""

    success: bool
    path_planned: bool
    already_at_destination: bool
    message: str


class MovementApplicationService:
    """移動に関するユースケースを統合するアプリケーションサービス"""
    
    def __init__(
        self,
        set_destination_service: SetDestinationService,
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
        self._set_destination_service = set_destination_service
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
        self._move_result_assembler = MoveResultAssembler(
            player_profile_repository=player_profile_repository,
            spot_repository=spot_repository,
        )
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

    def move_to_destination(
        self,
        player_id: int,
        destination_type: Literal["spot", "location", "object"],
        target_spot_id: int,
        target_location_area_id: Optional[int] = None,
        target_world_object_id: Optional[int] = None,
    ) -> MoveResultDto:
        """
        指定した目的地（スポット・ロケーション・オブジェクト）へ移動する。
        LLMエージェント・オーケストレータ等から呼ぶ統一API。内部で set_destination に委譲する。
        """
        if destination_type not in ("spot", "location", "object"):
            raise MovementInvalidException(
                f"destination_type は 'spot'、'location'、または 'object' で指定してください。取得値: {destination_type!r}",
                player_id,
            )
        if not isinstance(target_spot_id, (int, float)) or int(target_spot_id) <= 0:
            raise MovementInvalidException(
                f"target_spot_id は正の整数で指定してください。取得値: {target_spot_id!r}",
                player_id,
            )
        target_spot_id_int = int(target_spot_id)
        area_opt: Optional[int] = None
        object_id_opt: Optional[int] = None
        if destination_type == "location":
            if target_location_area_id is None:
                raise MovementInvalidException(
                    "destination_type が 'location' のときは target_location_area_id が必須です。",
                    player_id,
                )
            if not isinstance(target_location_area_id, (int, float)) or int(target_location_area_id) <= 0:
                raise MovementInvalidException(
                    f"target_location_area_id は正の整数で指定してください。取得値: {target_location_area_id!r}",
                    player_id,
                )
            area_opt = int(target_location_area_id)
        elif destination_type == "object":
            if target_world_object_id is None:
                raise MovementInvalidException(
                    "destination_type が 'object' のときは target_world_object_id が必須です。",
                    player_id,
                )
            if not isinstance(target_world_object_id, (int, float)) or int(target_world_object_id) <= 0:
                raise MovementInvalidException(
                    f"target_world_object_id は正の整数で指定してください。取得値: {target_world_object_id!r}",
                    player_id,
                )
            object_id_opt = int(target_world_object_id)
        command = SetDestinationCommand(
            player_id=player_id,
            destination_type=destination_type,
            target_spot_id=target_spot_id_int,
            target_location_area_id=area_opt,
            target_world_object_id=object_id_opt,
        )
        return self.set_destination(command)

    def set_destination(self, command: SetDestinationCommand) -> MoveResultDto:
        """目的地を設定する（内部・既存呼び出し用）。スポットまたはロケーション指定で座標不要。"""
        return self._execute_with_error_handling(
            operation=lambda: self._set_destination_impl(command),
            context={
                "action": "set_destination",
                "player_id": command.player_id,
                "target_spot_id": command.target_spot_id,
            }
        )

    def _set_destination_impl(self, command: SetDestinationCommand) -> MoveResultDto:
        with self._unit_of_work:
            result = self._set_destination_service.resolve_and_calculate_path(command)

            player_status = self._player_status_repository.find_by_id(PlayerId(command.player_id))
            current_spot_id = player_status.current_spot_id
            current_coord = player_status.current_coordinate
            current_tick = self._time_provider.get_current_tick().value

            if result.success:
                if result.already_at_destination:
                    return self._move_result_assembler.create_success(
                        player_status,
                        current_spot_id,
                        current_coord,
                        current_coord,
                        current_tick,
                        result.message,
                    )
                if result.path_found and result.temp_goal is not None and result.path is not None:
                    player_status.set_destination(
                        result.temp_goal,
                        result.path,
                        goal_destination_type=result.goal_destination_type,
                        goal_spot_id=result.goal_spot_id,
                        goal_location_area_id=result.goal_location_area_id,
                        goal_world_object_id=result.goal_world_object_id,
                    )
                    self._player_status_repository.save(player_status)
                    return self._move_result_assembler.create_success(
                        player_status,
                        current_spot_id,
                        current_coord,
                        current_coord,
                        current_tick,
                        result.message,
                    )

            return self._move_result_assembler.create_failure(
                command.player_id,
                result.message,
                player_status,
            )

    def replan_path_to_coordinate_in_current_unit_of_work(
        self,
        player_id: int,
        target_spot_id: int,
        target_coordinate: Coordinate,
    ) -> MovementReplanResult:
        """Replan a stored path toward an exact coordinate without consuming a step."""
        return self._execute_with_error_handling(
            operation=lambda: self._replan_path_to_coordinate_core(
                player_id=player_id,
                target_spot_id=SpotId(target_spot_id),
                target_coordinate=target_coordinate,
            ),
            context={
                "action": "replan_path_to_coordinate",
                "player_id": player_id,
                "target_spot_id": target_spot_id,
            },
        )

    def _replan_path_to_coordinate_core(
        self,
        player_id: int,
        target_spot_id: SpotId,
        target_coordinate: Coordinate,
    ) -> MovementReplanResult:
        result = self._set_destination_service.calculate_path_to_coordinate(
            player_id=player_id,
            target_spot_id=target_spot_id,
            target_coordinate=target_coordinate,
        )

        player_status = self._player_status_repository.find_by_id(PlayerId(player_id))
        if not player_status:
            raise PlayerNotFoundException(player_id)

        if result.already_at_destination or (not result.success and not result.path_planned):
            player_status.clear_path()
            self._player_status_repository.save(player_status)
            return MovementReplanResult(
                success=result.success,
                path_planned=result.path_planned,
                already_at_destination=result.already_at_destination,
                message=result.message,
            )

        if result.path_planned and result.temp_goal is not None and result.path is not None and result.goal_spot_id is not None:
            player_status.set_destination(
                result.temp_goal,
                result.path,
                goal_spot_id=result.goal_spot_id,
            )
            self._player_status_repository.save(player_status)

        return MovementReplanResult(
            success=result.success,
            path_planned=result.path_planned,
            already_at_destination=result.already_at_destination,
            message=result.message,
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

    def tick_movement_in_current_unit_of_work(self, player_id: int) -> MoveResultDto:
        """既存の UnitOfWork 内で継続移動を 1 ステップ進める内部向け API。"""
        command = TickMovementCommand(player_id=player_id)
        return self._execute_with_error_handling(
            operation=lambda: self._tick_movement_core(command),
            context={
                "action": "tick_movement",
                "player_id": command.player_id,
            },
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
                return self._move_result_assembler.create_failure(command.player_id, "現在地が不明です", player_status)
            coord = player_status.current_coordinate
            return self._move_result_assembler.create_success(
                player_status,
                player_status.current_spot_id,
                coord,
                coord,
                0,
                "移動を中断しました。",
            )

    def _tick_movement_impl(self, command: TickMovementCommand) -> MoveResultDto:
        with self._unit_of_work:
            return self._tick_movement_core(command)

    def _tick_movement_core(self, command: TickMovementCommand) -> MoveResultDto:
        player_id = PlayerId(command.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status:
            raise PlayerNotFoundException(command.player_id)

        next_coord = player_status.advance_path()
        if not next_coord:
            return self._move_result_assembler.create_failure(command.player_id, "移動計画がないか、既に到着しています", player_status)
        
        # 移動実行
        try:
            result = self._execute_movement_step(
                command.player_id, target_coordinate=next_coord, player_status=player_status
            )
            if not result.success:
                player_status.clear_path()
                self._player_status_repository.save(player_status)
                return result

            # 到着判定（スポット到着 or ロケーション到着 or オブジェクト隣接）
            player_status = self._player_status_repository.find_by_id(player_id)
            physical_map = self._physical_map_repository.find_by_spot_id(
                player_status.current_spot_id
            ) if player_status.current_spot_id else None
            arrival_result = ArrivalPolicy.check(player_status, physical_map)
            if arrival_result in (ArrivalCheckResult.ARRIVED, ArrivalCheckResult.GOAL_DISAPPEARED):
                if arrival_result == ArrivalCheckResult.GOAL_DISAPPEARED:
                    self._logger.debug(
                        "Goal disappeared (location or object), cleared path"
                    )
                player_status.clear_path()
                self._player_status_repository.save(player_status)

            return result
        except (MovementInvalidException, PathBlockedException, ActorBusyException, PlayerStaminaExhaustedException) as e:
            # 業務的な失敗の場合は、経路をクリアした状態を保存して正常終了（失敗DTO）を返す
            player_status.clear_path()
            self._player_status_repository.save(player_status)
            return self._move_result_assembler.create_failure(command.player_id, str(e), player_status)

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
            return self._move_result_assembler.create_failure(player_id_int, "現在行動できません", player_status)

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
            if to_coord != from_coord:
                direction = from_coord.direction_to(to_coord)
        else:
            raise MovementInvalidException("No movement target specified", player_id_int)

        # 3.5 ゲートウェイ遷移条件の評価（該当ゲートウェイがある場合のみ）
        transition_result = self._evaluate_gateway_transition_conditions(
            physical_map, to_coord, current_spot_id, player_id_int, player_status
        )
        if transition_result is not None:
            allowed, failure_message = transition_result
            if not allowed:
                return self._move_result_assembler.create_failure(
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
            if direction is not None:
                actor.turn(direction)
            physical_map.move_object(world_object_id, to_coord, current_tick, actor.capability)
            
            # スタミナ消費
            player_status.consume_stamina(int(stamina_cost))
            
            # プレイヤー状態の更新（座標）
            player_status.update_location(
                current_spot_id,
                to_coord,
                current_tick=current_tick,
            )
            
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
            
            return self._move_result_assembler.create_success(player_status, current_spot_id, from_coord, player_status.current_coordinate, actor.busy_until.value, message)

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
