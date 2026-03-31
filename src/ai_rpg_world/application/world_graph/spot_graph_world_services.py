"""
スポットグラフモード用のサービス束。

2D タイルマップモードでは本束を組み立てず、既存の WorldSimulation / Movement 系のみを使う。
ゲーム起動設定で `SpotGraphWorldServices` を注入するか否かを切り替える想定。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.application.world_graph.spot_exploration_application_service import (
    SpotExplorationApplicationService,
)
from ai_rpg_world.application.world_graph.spot_exploration_progress_store import (
    ISpotExplorationProgressStore,
    InMemorySpotExplorationProgressStore,
)
from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_context import (
    SpotGraphTravelContextProvider,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import (
    SpotGraphTravelStageService,
)
from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)


@dataclass(frozen=True)
class SpotGraphWorldServices:
    """スポットグラフ用アプリケーションサービスと共有状態（移動は任意で同梱）。"""

    interaction: SpotInteractionApplicationService
    exploration: SpotExplorationApplicationService
    world_flags: MutableWorldFlagState
    game_end_evaluator: GameEndConditionEvaluator
    exploration_progress: ISpotExplorationProgressStore
    movement: Optional[SpotGraphMovementApplicationService] = None
    travel_stage: Optional[SpotGraphTravelStageService] = None


def create_spot_graph_world_services(
    spot_graph_repository: ISpotGraphRepository,
    spot_interior_repository: ISpotInteriorRepository,
    player_status_repository: PlayerStatusRepository,
    player_inventory_repository: PlayerInventoryRepository,
    item_repository: ItemRepository,
    item_spec_repository: ItemSpecRepository,
    *,
    world_flag_state: Optional[MutableWorldFlagState] = None,
    exploration_progress_store: Optional[ISpotExplorationProgressStore] = None,
    movement_service: Optional[SpotGraphMovementApplicationService] = None,
    travel_context: Optional[SpotGraphTravelContextProvider] = None,
    travel_stage: Optional[SpotGraphTravelStageService] = None,
) -> SpotGraphWorldServices:
    """スポットグラフ用サービス束を組み立てる。

    Args:
        movement_service: スポット間移動を使う場合に渡す（Step 3）。
        travel_context / travel_stage: 継続移動ステージを同梱する場合。`travel_stage` を直接渡すか、
            `travel_context` のみ渡して `movement_service` と `player_status_repository` から
            ステージを生成することもできる（呼び出し元の方針で選択）。
    """
    flags = world_flag_state or MutableWorldFlagState()
    progress = exploration_progress_store or InMemorySpotExplorationProgressStore()

    interaction = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repository,
        spot_interior_repository=spot_interior_repository,
        player_inventory_repository=player_inventory_repository,
        item_repository=item_repository,
        item_spec_repository=item_spec_repository,
        world_flag_state=flags,
    )
    exploration = SpotExplorationApplicationService(
        spot_graph_repository=spot_graph_repository,
        spot_interior_repository=spot_interior_repository,
        player_inventory_repository=player_inventory_repository,
        item_repository=item_repository,
        item_spec_repository=item_spec_repository,
        world_flag_state=flags,
        exploration_progress_store=progress,
    )
    resolved_travel_stage = travel_stage
    if resolved_travel_stage is None and travel_context is not None and movement_service is not None:
        resolved_travel_stage = SpotGraphTravelStageService(
            player_status_repository=player_status_repository,
            movement_service=movement_service,
            travel_context=travel_context,
        )

    return SpotGraphWorldServices(
        interaction=interaction,
        exploration=exploration,
        world_flags=flags,
        game_end_evaluator=GameEndConditionEvaluator(),
        exploration_progress=progress,
        movement=movement_service,
        travel_stage=resolved_travel_stage,
    )
