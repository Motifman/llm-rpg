"""SpotGraphTravelStageService が 1 人の移動の例外を、方針に従ってその 1 人だけ取りやめるか止めるかを保証する。"""

from __future__ import annotations

import pytest
from tests.domain.player.aggregate.test_player_status_aggregate import create_test_status_aggregate
from tests.support.trace_recorders import CollectingTraceRecorder

from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import (
    SpotGraphTravelStageService,
)
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
    WorldTickFailurePolicy,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)


class _NoItemsContext:
    def owned_item_spec_ids_for(self, player_id: PlayerId) -> frozenset[ItemSpecId]:
        return frozenset()

    def world_flags(self) -> frozenset[str]:
        return frozenset()


def _traveling_players(repo: InMemoryPlayerStatusRepository, *player_ids: int) -> None:
    for player_id in player_ids:
        status = create_test_status_aggregate(player_id=player_id)
        status.set_spot_navigation_state(
            PlayerSpotNavigationState.begin_travel(
                route=(SpotId.create(1), SpotId.create(2)),
                leg_connection_ids=(ConnectionId.create(1),),
                leg_travel_ticks=(1,),
            )
        )
        repo.save(status)


class _FirstPlayerFails:
    def __init__(self, repo: InMemoryPlayerStatusRepository) -> None:
        self._repo = repo

    def cancel_spot_travel(self, player_id: PlayerId) -> None:
        raise AssertionError(f"unexpected cancellation: {player_id}")

    def advance_spot_travel_one_tick(self, player_id, items, flags) -> None:
        if player_id == PlayerId(1):
            raise RuntimeError("passage closed while traveling")
        status = self._repo.find_by_id(player_id)
        status.set_spot_navigation_state(PlayerSpotNavigationState.at_rest(SpotId.create(2)))
        self._repo.save(status)


def _stage(
    policy: WorldTickFailurePolicy, recorder: CollectingTraceRecorder, arrived: list[int]
) -> SpotGraphTravelStageService:
    repo = InMemoryPlayerStatusRepository()
    _traveling_players(repo, 1, 2)
    return SpotGraphTravelStageService(
        repo,
        _FirstPlayerFails(repo),  # type: ignore[arg-type]
        _NoItemsContext(),
        on_arrival=lambda player_id: arrived.append(int(player_id)),
        failure_isolator=WorldTickFailureIsolator(policy=policy, trace_recorder_provider=lambda: recorder),
    )


def _skipped(recorder: CollectingTraceRecorder) -> list[tuple[str, object, int | None]]:
    return [
        (e.payload["stage"], e.payload["target_id"], e.player_id)
        for e in recorder.of_kind(TraceEventKind.WORLD_TICK_UNIT_FAILED)
    ]


class TestTravelStageFailureIsolation:
    """移動の段で 1 人の移動が例外を出したときの扱い。"""

    def test_isolate_skips_the_failed_player_and_moves_the_next(self) -> None:
        """isolate で 1 人目の移動が例外を出すと、その人だけを travel として trace に残し、同じ tick の 2 人目は到着する。"""
        recorder = CollectingTraceRecorder()
        arrived: list[int] = []
        stage = _stage(WorldTickFailurePolicy.ISOLATE, recorder, arrived)

        stage.run(WorldTick(4))

        assert arrived == [2]
        assert _skipped(recorder) == [("travel", 1, 1)]

    def test_fail_fast_stops_at_the_failed_player(self) -> None:
        """fail_fast で 1 人目の移動が例外を出すと、trace に残してから止め、2 人目は動かさない。"""
        recorder = CollectingTraceRecorder()
        arrived: list[int] = []
        stage = _stage(WorldTickFailurePolicy.FAIL_FAST, recorder, arrived)

        with pytest.raises(RuntimeError, match="passage closed"):
            stage.run(WorldTick(4))

        assert arrived == []
        assert _skipped(recorder) == [("travel", 1, 1)]


class TestTravelStageFollowUpFailures:
    """確定済みの移動に続く通知の失敗を、止めずに trace へ残すこと。"""

    def test_failing_arrival_observer_is_recorded_and_later_observers_still_run(self) -> None:
        """isolate で到着の観察者が例外を出すと、travel.arrival_observer として続けた失敗を残し、後ろの観察者 (ターンの再開など) は呼ばれる。"""
        recorder = CollectingTraceRecorder()
        repo = InMemoryPlayerStatusRepository()
        _traveling_players(repo, 2)
        resumed: list[int] = []
        stage = SpotGraphTravelStageService(
            repo,
            _FirstPlayerFails(repo),  # type: ignore[arg-type]
            _NoItemsContext(),
            failure_isolator=WorldTickFailureIsolator(
                policy=WorldTickFailurePolicy.ISOLATE, trace_recorder_provider=lambda: recorder
            ),
        )

        def broken_history(player_id: PlayerId) -> None:
            raise RuntimeError("history store down")

        stage.add_arrival_observer(broken_history)
        stage.add_arrival_observer(lambda player_id: resumed.append(int(player_id)))

        stage.run(WorldTick(4))

        assert resumed == [2]
        failures = recorder.of_kind(TraceEventKind.WORLD_TICK_UNIT_FAILED)
        assert [(e.tick, e.payload["stage"], e.payload["target_id"], e.payload["continued"]) for e in failures] == [
            (4, "travel.arrival_observer", 2, True)
        ]
