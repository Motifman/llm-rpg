"""Movement サービスの wiring。SetDestinationService・MovementStepExecutor・MovementApplicationService を明示的に注入する。

create_llm_agent_wiring 等に movement_service を渡す際、本モジュールの create_movement_application_service を用いて
構築すると、依存関係が明示的になる。
"""

from typing import Optional

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.repository.transition_policy_repository import ITransitionPolicyRepository
from ai_rpg_world.domain.world.service.global_pathfinding_service import GlobalPathfindingService
from ai_rpg_world.domain.world.service.movement_config_service import MovementConfigService
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world.services.set_destination_service import SetDestinationService
from ai_rpg_world.application.world.services.movement_step_executor import MovementStepExecutor
from ai_rpg_world.application.world.services.movement_service import MovementApplicationService
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
)


def create_movement_application_service(
    *,
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
) -> MovementApplicationService:
    """
    SetDestinationService・MovementStepExecutor・MovementApplicationService を構築し、
    MovementApplicationService を返す。

    create_llm_agent_wiring(movement_service=create_movement_application_service(...)) のように使用する。

    Args:
        player_status_repository: プレイヤー状態リポジトリ
        player_profile_repository: プレイヤープロフィールリポジトリ
        physical_map_repository: 物理マップリポジトリ
        spot_repository: スポットリポジトリ
        connected_spots_provider: 接続スポットプロバイダ
        global_pathfinding_service: グローバル経路探索サービス
        movement_config_service: 移動設定サービス
        time_provider: ゲーム時間プロバイダ
        unit_of_work: Unit of Work
        transition_policy_repository: ゲートウェイ遷移ポリシー（省略可）
        transition_condition_evaluator: 遷移条件評価器（省略可）

    Returns:
        MovementApplicationService: 構築済みの MovementApplicationService
    """
    set_destination_service = SetDestinationService(
        player_status_repository=player_status_repository,
        physical_map_repository=physical_map_repository,
        connected_spots_provider=connected_spots_provider,
        global_pathfinding_service=global_pathfinding_service,
    )
    movement_step_executor = MovementStepExecutor(
        player_status_repository=player_status_repository,
        player_profile_repository=player_profile_repository,
        physical_map_repository=physical_map_repository,
        spot_repository=spot_repository,
        movement_config_service=movement_config_service,
        time_provider=time_provider,
        unit_of_work=unit_of_work,
        transition_policy_repository=transition_policy_repository,
        transition_condition_evaluator=transition_condition_evaluator,
    )
    return MovementApplicationService(
        set_destination_service=set_destination_service,
        movement_step_executor=movement_step_executor,
        player_status_repository=player_status_repository,
        player_profile_repository=player_profile_repository,
        physical_map_repository=physical_map_repository,
        spot_repository=spot_repository,
        connected_spots_provider=connected_spots_provider,
        global_pathfinding_service=global_pathfinding_service,
        movement_config_service=movement_config_service,
        time_provider=time_provider,
        unit_of_work=unit_of_work,
    )


__all__ = ["create_movement_application_service"]
