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
        self._eliminated_checker: Optional[Callable[[PlayerId], bool]] = None
        self._departed_checker: Optional[Callable[[PlayerId], bool]] = None

    def set_on_arrival(self, callback: Optional[Callable[[PlayerId], None]]) -> None:
        """到着コールバックを後付けで差し替える。

        wiring 順序の都合で LLM turn trigger が travel_stage より後に
        構築されるため、構築済みの travel_stage に後から差し込めるよう
        setter を用意している。
        """
        self._on_arrival = callback

    def set_eliminated_checker(
        self,
        checker: Optional[Callable[[PlayerId], bool]],
    ) -> None:
        """盤から排除済みの player 判定を、outcome registry 構築後に受け取る。

        travel stage は outcome registry より先に構築されるため、
        ``set_on_arrival`` と同じく後付け配線にする。未配線の構成では
        従来どおり、排除済みとは判定しない。
        """
        self._eliminated_checker = checker

    def set_departed_checker(
        self, checker: Optional[Callable[[PlayerId], bool]]
    ) -> None:
        """有効な幽霊は is_down / DEAD でも移動予約を消化できるようにする。"""
        self._departed_checker = checker

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
            is_eliminated = (
                self._eliminated_checker(status.player_id)
                if self._eliminated_checker is not None
                else False
            )
            is_departed = (
                self._departed_checker(status.player_id)
                if self._departed_checker is not None
                else False
            )
            if (is_eliminated or status.is_down) and not is_departed:
                # 移動を予約した同じ tick に倒されても、次の tick 境界で
                # 予約だけを消化して死体を動かしてはいけない。run 012 では
                # 殺害現場が連絡通路なのに死体が物資庫へ移り、会議の位置情報
                # まで誤った。予約を作る各入口ではなく、全予約が通る消化側で
                # 取り消すことで、新しい予約入口にも同じ不変条件を効かせる。
                # 追放は is_down を立てず graph から外れるため、終局判定も
                # ここで合わせて見ないと次の移動消化で例外になり続ける。
                self._movement_service.cancel_spot_travel(status.player_id)
                continue
            was_traveling.append(status.player_id)

        for pid in was_traveling:
            self._movement_service.advance_spot_travel_one_tick(
                pid,
                self._travel_context.owned_item_spec_ids_for(pid),
                self._travel_context.world_flags(),
            )
            # playerごとの移動commandが確定した直後に到着を通知する。後続playerの
            # commandが失敗しても、既に到着済みのplayerを眠らせたままにしない。
            if self._on_arrival is None:
                continue
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
