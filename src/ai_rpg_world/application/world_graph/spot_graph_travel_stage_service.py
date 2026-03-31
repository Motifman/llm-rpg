from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_context import (
    SpotGraphTravelContextProvider,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository


class SpotGraphTravelStageService:
    """ワールドティックごとに、スポット間移動中のプレイヤーを進める。"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        movement_service: SpotGraphMovementApplicationService,
        travel_context: SpotGraphTravelContextProvider,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._movement_service = movement_service
        self._travel_context = travel_context

    def run(self, current_tick: WorldTick) -> None:
        del current_tick  # 将来: ログやスケジュールに使用
        for status in self._player_status_repository.find_all():
            nav = status.spot_navigation_state
            if nav is None or not nav.is_traveling:
                continue
            self._movement_service.advance_spot_travel_one_tick(
                status.player_id,
                self._travel_context.owned_item_spec_ids_for(status.player_id),
                self._travel_context.world_flags(),
            )
