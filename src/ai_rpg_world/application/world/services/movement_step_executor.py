"""MovementStepExecutor: 1 ステップの移動実行とスタミナ消費を担当するアプリケーションサービス。

MovementApplicationService から移動ステップ実行の責務を分離する。
ゲートウェイ遷移条件評価とスタミナコスト計算を含む。
"""

from typing import Optional, Protocol, Tuple

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.repository.transition_policy_repository import ITransitionPolicyRepository
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.service.movement_config_service import MovementConfigService
from ai_rpg_world.domain.world.service.weather_effect_service import WeatherEffectService
from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent
from ai_rpg_world.domain.world.exception.map_exception import (
    ObjectNotFoundException,
    TileNotFoundException,
    InvalidMovementException,
    ActorBusyException as DomainActorBusyException,
)
from ai_rpg_world.application.world.services.move_result_assembler import MoveResultAssembler
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
    TransitionContext,
)
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world.contracts.dtos import MoveResultDto
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
    MovementInvalidException,
    PlayerStaminaExhaustedException,
    PathBlockedException,
    ActorBusyException,
)


class _SyncEventDispatcherProtocol(Protocol):
    def flush_sync_events(self) -> None: ...


class MovementStepExecutor:
    """1 ステップの移動実行を担当するアプリケーションサービス。"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: PhysicalMapRepository,
        spot_repository: SpotRepository,
        movement_config_service: MovementConfigService,
        time_provider: GameTimeProvider,
        unit_of_work: UnitOfWork,
        transition_policy_repository: Optional[ITransitionPolicyRepository] = None,
        transition_condition_evaluator: Optional[TransitionConditionEvaluator] = None,
        sync_event_dispatcher: Optional["_SyncEventDispatcherProtocol"] = None,
    ):
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
        self._spot_repository = spot_repository
        self._movement_config_service = movement_config_service
        self._time_provider = time_provider
        self._unit_of_work = unit_of_work
        self._transition_policy_repository = transition_policy_repository
        self._transition_condition_evaluator = transition_condition_evaluator
        self._sync_event_dispatcher = sync_event_dispatcher
        self._move_result_assembler = MoveResultAssembler(
            player_profile_repository=player_profile_repository,
            spot_repository=spot_repository,
        )

    def execute_movement_step(
        self,
        player_id_int: int,
        direction: Optional[DirectionEnum] = None,
        target_coordinate: Optional[Coordinate] = None,
        player_status: Optional[PlayerStatusAggregate] = None,
    ) -> MoveResultDto:
        """
        移動の 1 ステップを実行する。

        Args:
            player_id_int: プレイヤー ID
            direction: 移動方向（方向指定移動時）
            target_coordinate: 移動先座標（座標指定移動時）
            player_status: 既に取得済みのプレイヤー状態（省略時はリポジトリから取得）

        Returns:
            MoveResultDto: 移動結果

        Raises:
            PlayerNotFoundException: プレイヤーが存在しない
            MapNotFoundException: マップが存在しない
            MovementInvalidException: 行動不可、マップ外、オブジェクトなし、目標未指定
            PlayerStaminaExhaustedException: スタミナ不足
            PathBlockedException: 移動先がブロックされている
            ActorBusyException: アクターがビジー状態
        """
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        player_id = PlayerId(player_id_int)
        current_tick = self._time_provider.get_current_tick()

        if not player_status:
            player_status = self._player_status_repository.find_by_id(player_id)
            if not player_status:
                raise PlayerNotFoundException(player_id_int)

        # 1. 基本状態チェック（戦闘不能など）
        if not player_status.can_act():
            return self._move_result_assembler.create_failure(
                player_id_int, "現在行動できません", player_status
            )

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
            raise MovementInvalidException(
                "Player object not found in physical map", player_id_int
            )

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
                raise PlayerStaminaExhaustedException(
                    player_id_int, stamina_cost, player_status.stamina.value
                )

            # 5. ドメインロジックの実行（物理マップ内移動）
            if direction is not None:
                actor.turn(direction)
            physical_map.move_object(
                world_object_id, to_coord, current_tick, actor.capability
            )

            # スタミナ消費
            player_status.consume_stamina(int(stamina_cost))

            # プレイヤー状態の更新（座標）
            player_status.update_location(
                current_spot_id,
                to_coord,
                current_tick=current_tick,
            )

            # 6. イベント収集と後処理
            message = "移動しました"
            if any(
                isinstance(e, GatewayTriggeredEvent)
                for e in physical_map.get_events()
            ):
                message = "マップを移動しました"

            # 保存
            self._physical_map_repository.save(physical_map)
            self._player_status_repository.save(player_status)

            # 同期イベントの即時実行（マップ遷移などを反映させるため）
            if self._sync_event_dispatcher is not None:
                self._sync_event_dispatcher.flush_sync_events()

            # 状態が変わっている可能性があるため再ロード
            player_status = self._player_status_repository.find_by_id(player_id)

            return self._move_result_assembler.create_success(
                player_status,
                current_spot_id,
                from_coord,
                player_status.current_coordinate,
                actor.busy_until.value,
                message,
            )

        except DomainActorBusyException:
            raise ActorBusyException(
                player_id_int,
                int(actor.busy_until.value - current_tick.value),
            )
        except (TileNotFoundException, InvalidMovementException):
            raise PathBlockedException(
                player_id_int, {"x": to_coord.x, "y": to_coord.y, "z": to_coord.z}
            )

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
                    return self._transition_condition_evaluator.evaluate(
                        conditions, context
                    )
                break
        return None

    def _compute_stamina_cost_for_move(
        self, physical_map: PhysicalMapAggregate, to_coord: Coordinate
    ) -> float:
        """移動先タイルのスタミナコスト（天候倍率込み）を計算する。"""
        tile = physical_map.get_tile(to_coord)
        base_stamina_cost = self._movement_config_service.get_stamina_cost(
            tile.terrain_type
        )
        weather_multiplier = WeatherEffectService.calculate_stamina_multiplier(
            physical_map.weather_state,
            physical_map.environment_type,
        )
        return base_stamina_cost * weather_multiplier
