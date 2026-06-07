from __future__ import annotations

from typing import Callable, Optional

from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_context import (
    SpotGraphTravelContextProvider,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class SpotGraphTravelStageService:
    """ワールドティックごとに、スポット間移動中のプレイヤーを進める。

    ``#404`` 修正後: travel 完了 (is_traveling=True → False の遷移) を検知し、
    ``on_arrival`` コールバックを呼ぶ。これにより移動者の LLM ターンを
    「到着まで sleep、到着時に起床」させる。コールバックは LLM turn trigger
    の ``schedule_turn`` を渡す想定だが、travel_stage は LLM 層を知らないため
    関数オブジェクトを受け取る形にしている。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        movement_service: SpotGraphMovementApplicationService,
        travel_context: SpotGraphTravelContextProvider,
        on_arrival: Optional[Callable[[PlayerId], None]] = None,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._movement_service = movement_service
        self._travel_context = travel_context
        self._on_arrival = on_arrival

    def set_on_arrival(self, callback: Optional[Callable[[PlayerId], None]]) -> None:
        """到着コールバックを後付けで差し替える。

        wiring 順序の都合で LLM turn trigger が travel_stage より後に
        構築されるため、構築済みの travel_stage に後から差し込めるよう
        setter を用意している。
        """
        self._on_arrival = callback

    def run(self, current_tick: WorldTick) -> None:
        del current_tick  # 将来: ログやスケジュールに使用
        # 進める前に「移動中だった player」のスナップショットを取る。
        # advance_spot_travel_one_tick 後に再 fetch して is_traveling
        # 遷移を比較するため。
        was_traveling: list[PlayerId] = []
        for status in self._player_status_repository.find_all():
            nav = status.spot_navigation_state
            if nav is None or not nav.is_traveling:
                continue
            was_traveling.append(status.player_id)

        for pid in was_traveling:
            self._movement_service.advance_spot_travel_one_tick(
                pid,
                self._travel_context.owned_item_spec_ids_for(pid),
                self._travel_context.world_flags(),
            )

        # 到着 (is_traveling=True → False) を検知して on_arrival 通知。
        # advance 後の player_status を再 fetch する。
        if self._on_arrival is None:
            return
        for pid in was_traveling:
            status_after = self._player_status_repository.find_by_id(pid)
            if status_after is None:
                continue
            nav_after = status_after.spot_navigation_state
            if nav_after is not None and nav_after.is_traveling:
                continue
            # 遷移検出: 通知する。コールバックの例外は travel stage 全体を
            # 倒さない (post-commit hook 同等の責務分離)。
            try:
                self._on_arrival(pid)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "on_arrival callback failed for player %s", pid.value
                )
