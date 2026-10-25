from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
    SpotTravelBlocked,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_context import (
    SpotGraphTravelContextProvider,
)
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


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
        on_arrival: Callable[[PlayerId], None] | None = None,
        on_travel_tick_committed: Callable[[PlayerId], None] | None = None,
        failure_isolator: WorldTickFailureIsolator | None = None,
    ) -> None:
        self._failure_isolator = failure_isolator or WorldTickFailureIsolator.fail_fast()
        self._player_status_repository = player_status_repository
        self._movement_service = movement_service
        self._travel_context = travel_context
        self._on_travel_tick_committed = on_travel_tick_committed
        # **観察者は list で持つ。** 単一 callback の上書き API だったころは、
        # 後から配線する側 (LLM の手番再開) が先に置かれた hook
        # (encounter 記録・到着の履歴) を黙って消していた。実走経路でだけ
        # 発火しない hook が生まれる形で、静かな失敗そのものだった。
        self._arrival_observers: list[Callable[[PlayerId], None]] = [on_arrival] if on_arrival is not None else []
        self._blocked_observers: list[Callable[[PlayerId, SpotTravelBlocked], None]] = []
        self._eliminated_checker: Callable[[PlayerId], bool] | None = None
        self._departed_checker: Callable[[PlayerId], bool] | None = None
        # 確定後の通知の失敗を trace に残すときの tick。run の入口で更新する。
        self._current_tick: WorldTick | None = None

    def add_arrival_observer(self, callback: Callable[[PlayerId], None]) -> None:
        """到着の観察者を足す。**既にいる観察者は消さない。**

        wiring 順序の都合で LLM turn trigger が travel_stage より後に
        構築されるため、構築済みの travel_stage に後から差し込む必要が
        ある。上書きにすると、先に置かれた hook が実走経路でだけ消える。
        """
        self._arrival_observers.append(callback)

    def add_blocked_observer(self, callback: Callable[[PlayerId, SpotTravelBlocked], None]) -> None:
        """区間が閉じて移動を取りやめたときの観察者を足す。到着の観察者は呼ばない。"""
        self._blocked_observers.append(callback)

    def set_on_arrival(self, callback: Callable[[PlayerId], None] | None) -> None:
        """後方互換の入口。**観察者を置き換えるのではなく足す。**

        `None` は「観察者を消す」意味で残す (テストが到着通知を切るのに
        使う)。それ以外は `add_arrival_observer` と同じ。
        """
        if callback is None:
            self._arrival_observers = []
            return
        self.add_arrival_observer(callback)

    def set_on_travel_tick_committed(
        self,
        callback: Callable[[PlayerId], None] | None,
    ) -> None:
        """player 単位の移動 command 確定を観測する callback を設定する。"""
        self._on_travel_tick_committed = callback

    def set_eliminated_checker(
        self,
        checker: Callable[[PlayerId], bool] | None,
    ) -> None:
        """盤から排除済みの player 判定を、outcome registry 構築後に受け取る。

        travel stage は outcome registry より先に構築されるため、
        ``set_on_arrival`` と同じく後付け配線にする。未配線の構成では
        従来どおり、排除済みとは判定しない。
        """
        self._eliminated_checker = checker

    def set_departed_checker(self, checker: Callable[[PlayerId], bool] | None) -> None:
        """有効な幽霊は is_down / DEAD でも移動予約を消化できるようにする。"""
        self._departed_checker = checker

    def run(self, current_tick: WorldTick) -> None:
        self._current_tick = current_tick
        # 進める前に「移動中だった player」のスナップショットを取る。
        # advance_spot_travel_one_tick 後に再 fetch して is_traveling
        # 遷移を比較するため。
        was_traveling: list[PlayerId] = []
        destinations: dict[PlayerId, SpotId] = {}
        for status in self._player_status_repository.find_all():
            nav = status.spot_navigation_state
            if nav is None or not nav.is_traveling:
                continue
            is_eliminated = (
                self._eliminated_checker(status.player_id) if self._eliminated_checker is not None else False
            )
            is_departed = self._departed_checker(status.player_id) if self._departed_checker is not None else False
            if (is_eliminated or status.is_down) and not is_departed:
                # 移動を予約した同じ tick に倒されても、次の tick 境界で
                # 予約だけを消化して死体を動かしてはいけない。run 012 では
                # 殺害現場が連絡通路なのに死体が物資庫へ移り、会議の位置情報
                # まで誤った。予約を作る各入口ではなく、全予約が通る消化側で
                # 取り消すことで、新しい予約入口にも同じ不変条件を効かせる。
                # 追放は is_down を立てず graph から外れるため、終局判定も
                # ここで合わせて見ないと次の移動消化で例外になり続ける。
                with self._player_unit(current_tick, status.player_id):
                    self._movement_service.cancel_spot_travel(status.player_id)
                continue
            was_traveling.append(status.player_id)
            destinations[status.player_id] = nav.route[-1]

        for pid in was_traveling:
            with self._player_unit(current_tick, pid):
                try:
                    result = self._movement_service.advance_spot_travel_one_tick(
                        pid,
                        self._travel_context.owned_item_spec_ids_for(pid),
                        self._travel_context.world_flags(),
                    )
                except CommandPostCommitException:
                    # commandの状態は確定済みである。cleanup/handoff失敗を返す前に、
                    # 確定に追随する計測と到着通知を失わない。結果が返らないので、
                    # 取りやめて止まったのか着いたのかは行き先と比べて決める。
                    self._notify_committed_travel(pid, destinations[pid])
                    raise
                blocked = result.blocked if result is not None else None
                if blocked is None:
                    self._notify_committed_travel(pid, destinations[pid])
                else:
                    self._notify_blocked_travel(pid, blocked)

    def _player_unit(self, current_tick: WorldTick, player_id: PlayerId) -> AbstractContextManager[None]:
        return self._failure_isolator.unit(
            stage="travel",
            tick=current_tick,
            target_kind="player",
            target_id=player_id.value,
            player_id=player_id.value,
        )

    def _notify_blocked_travel(self, player_id: PlayerId, blocked: SpotTravelBlocked) -> None:
        """取りやめた移動の計測と通知を、いずれも最善努力で行う。"""
        self._notify_travel_tick_committed(player_id)
        for observer in tuple(self._blocked_observers):
            try:
                observer(player_id, blocked)
            except Exception as exc:
                self._record_follow_up_failure(exc, "travel.blocked_observer", player_id)

    def _notify_travel_tick_committed(self, player_id: PlayerId) -> None:
        if self._on_travel_tick_committed is None:
            return
        try:
            self._on_travel_tick_committed(player_id)
        except Exception as exc:
            self._record_follow_up_failure(exc, "travel.tick_committed_observer", player_id)

    def _notify_committed_travel(self, player_id: PlayerId, destination: SpotId) -> None:
        """確定済み移動の計測と到着通知を、いずれも最善努力で行う。"""
        self._notify_travel_tick_committed(player_id)
        # 到着 (is_traveling=True → False) を検知して on_arrival 通知。
        # advance 後の player_status を再 fetch する。
        if not self._arrival_observers:
            return
        try:
            status_after = self._player_status_repository.find_by_id(player_id)
            if status_after is None:
                return
            nav_after = status_after.spot_navigation_state
            if nav_after is not None and nav_after.is_traveling:
                return
            if nav_after is not None and nav_after.current_spot_id != destination:
                return
            # 遷移検出: 通知する。コールバックの例外は travel stage 全体を
            # 倒さない (post-commit hook 同等の責務分離)。
            for observer in tuple(self._arrival_observers):
                try:
                    observer(player_id)
                except Exception as exc:
                    self._record_follow_up_failure(exc, "travel.arrival_observer", player_id)
        except Exception as exc:
            self._record_follow_up_failure(exc, "travel.arrival_detection", player_id)

    def _record_follow_up_failure(self, exc: Exception, stage: str, player_id: PlayerId) -> None:
        self._failure_isolator.record_continued_failure(
            exc,
            stage=stage,
            tick=self._current_tick,
            target_kind="player",
            target_id=player_id.value,
            player_id=player_id.value,
        )
