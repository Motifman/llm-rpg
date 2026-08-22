from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

import pytest

from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import (
    SpotGraphTravelStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from tests.domain.player.aggregate.test_player_status_aggregate import create_test_status_aggregate


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _line_graph_three_spots(travel_ticks: int = 1) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_spot(_node(3))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="a",
            description="",
            travel_ticks=travel_ticks,
            is_bidirectional=False,
        )
    )
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(2),
            from_spot_id=SpotId.create(2),
            to_spot_id=SpotId.create(3),
            name="b",
            description="",
            travel_ticks=travel_ticks,
            is_bidirectional=False,
        )
    )
    g.place_entity(EntityId.create(1), SpotId.create(1))
    g.clear_events()
    return g


@dataclass
class _FixedContext:
    items: FrozenSet[ItemSpecId]
    flags: FrozenSet[str]

    def owned_item_spec_ids_for(self, player_id: PlayerId) -> FrozenSet[ItemSpecId]:
        del player_id
        return self.items

    def world_flags(self) -> FrozenSet[str]:
        return self.flags


def test_start_and_tick_reaches_destination() -> None:
    graph = _line_graph_three_spots(travel_ticks=1)
    graph_repo = InMemorySpotGraphRepository(graph)
    player_repo = InMemoryPlayerStatusRepository()
    player = create_test_status_aggregate(player_id=1)
    player_repo.save(player)

    svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
    ctx = _FixedContext(items=frozenset(), flags=frozenset())
    stage = SpotGraphTravelStageService(player_repo, svc, ctx)

    svc.start_travel_to_spot(PlayerId(1), SpotId.create(3), frozenset(), frozenset())

    loaded = player_repo.find_by_id(PlayerId(1))
    assert loaded is not None
    nav = loaded.spot_navigation_state
    assert nav is not None
    assert nav.is_traveling

    stage.run(WorldTick(1))
    stage.run(WorldTick(2))

    g2 = graph_repo.find_graph()
    assert g2.get_entity_spot(EntityId.create(1)) == SpotId.create(3)
    p2 = player_repo.find_by_id(PlayerId(1))
    assert p2 is not None
    assert p2.spot_navigation_state is not None
    assert not p2.spot_navigation_state.is_traveling
    assert p2.spot_navigation_state.current_spot_id == SpotId.create(3)


def test_ensure_spot_nav_syncs_from_graph() -> None:
    graph = _line_graph_three_spots()
    graph_repo = InMemorySpotGraphRepository(graph)
    player_repo = InMemoryPlayerStatusRepository()
    player_repo.save(create_test_status_aggregate(player_id=1))

    svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
    svc.start_travel_to_spot(PlayerId(1), SpotId.create(2), frozenset(), frozenset())

    p = player_repo.find_by_id(PlayerId(1))
    assert p is not None
    assert p.spot_navigation_state is not None
    assert p.spot_navigation_state.is_traveling


def test_move_sub_location() -> None:
    graph = _line_graph_three_spots()
    graph_repo = InMemorySpotGraphRepository(graph)
    player_repo = InMemoryPlayerStatusRepository()
    player_repo.save(create_test_status_aggregate(player_id=1))

    svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
    svc.move_to_sub_location(PlayerId(1), SubLocationId.create(7))

    p = player_repo.find_by_id(PlayerId(1))
    assert p is not None
    assert p.spot_navigation_state is not None
    assert p.spot_navigation_state.current_sub_location_id == SubLocationId.create(7)


def test_same_destination_op() -> None:
    graph = _line_graph_three_spots()
    graph_repo = InMemorySpotGraphRepository(graph)
    player_repo = InMemoryPlayerStatusRepository()
    player_repo.save(create_test_status_aggregate(player_id=1))

    svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
    svc.start_travel_to_spot(PlayerId(1), SpotId.create(1), frozenset(), frozenset())

    p = player_repo.find_by_id(PlayerId(1))
    assert p is not None
    assert p.spot_navigation_state is not None
    assert not p.spot_navigation_state.is_traveling


def test_first_arrival_callback_survives_a_later_player_failure() -> None:
    """先のplayerの確定済み到着は後続playerの失敗で失われない。"""
    player_repo = InMemoryPlayerStatusRepository()
    first = create_test_status_aggregate(player_id=1)
    first.set_spot_navigation_state(
        PlayerSpotNavigationState.begin_travel(
            route=(SpotId.create(1), SpotId.create(2)),
            leg_connection_ids=(ConnectionId.create(1),),
            leg_travel_ticks=(1,),
        )
    )
    second = create_test_status_aggregate(player_id=2)
    second.set_spot_navigation_state(
        PlayerSpotNavigationState.begin_travel(
            route=(SpotId.create(1), SpotId.create(2)),
            leg_connection_ids=(ConnectionId.create(1),),
            leg_travel_ticks=(1,),
        )
    )
    player_repo.save(first)
    player_repo.save(second)

    class _Movement:
        def cancel_spot_travel(self, player_id: PlayerId) -> None:
            raise AssertionError(f"unexpected cancellation: {player_id}")

        def advance_spot_travel_one_tick(self, player_id, items, flags) -> None:
            del items, flags
            if player_id == PlayerId(2):
                raise RuntimeError("second player failed")
            status = player_repo.find_by_id(player_id)
            assert status is not None
            status.set_spot_navigation_state(
                PlayerSpotNavigationState.at_rest(SpotId.create(2))
            )
            player_repo.save(status)

    arrived: list[int] = []
    committed: list[int] = []
    stage = SpotGraphTravelStageService(
        player_repo,
        _Movement(),  # type: ignore[arg-type]
        _FixedContext(items=frozenset(), flags=frozenset()),
        on_arrival=lambda player_id: arrived.append(int(player_id)),
        on_travel_tick_committed=lambda player_id: committed.append(int(player_id)),
    )

    with pytest.raises(RuntimeError, match="second player failed"):
        stage.run(WorldTick(1))

    assert arrived == [1]
    assert committed == [1]


class TestTravelStageEliminatedPlayer:
    """移動予約の消化時に、盤から排除済みの player を動かさない。"""

    def test_eliminated_player_has_the_reserved_travel_cancelled(self) -> None:
        """追放済みの移動中 player は、次の tick で現在地の at_rest に戻る。"""
        graph = _line_graph_three_spots(travel_ticks=1)
        graph_repo = InMemorySpotGraphRepository(graph)
        player_repo = InMemoryPlayerStatusRepository()
        player_repo.save(create_test_status_aggregate(player_id=1))
        svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
        stage = SpotGraphTravelStageService(
            player_repo,
            svc,
            _FixedContext(items=frozenset(), flags=frozenset()),
        )
        stage.set_eliminated_checker(lambda player_id: player_id == PlayerId(1))
        svc.start_travel_to_spot(
            PlayerId(1), SpotId.create(2), frozenset(), frozenset()
        )

        stage.run(WorldTick(1))

        player = player_repo.find_by_id(PlayerId(1))
        assert player is not None
        assert player.spot_navigation_state == PlayerSpotNavigationState.at_rest(
            SpotId.create(1)
        )
        assert graph_repo.find_graph().get_entity_spot(
            EntityId.create(1)
        ) == SpotId.create(1)

    def test_active_player_still_advances_reserved_travel(self) -> None:
        """退場していない移動中 player は、従来どおり次の spot へ進む。"""
        graph = _line_graph_three_spots(travel_ticks=1)
        graph_repo = InMemorySpotGraphRepository(graph)
        player_repo = InMemoryPlayerStatusRepository()
        player_repo.save(create_test_status_aggregate(player_id=1))
        svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
        stage = SpotGraphTravelStageService(
            player_repo,
            svc,
            _FixedContext(items=frozenset(), flags=frozenset()),
        )
        stage.set_eliminated_checker(lambda _player_id: False)
        svc.start_travel_to_spot(
            PlayerId(1), SpotId.create(2), frozenset(), frozenset()
        )

        stage.run(WorldTick(1))

        player = player_repo.find_by_id(PlayerId(1))
        assert player is not None
        assert player.spot_navigation_state == PlayerSpotNavigationState.at_rest(
            SpotId.create(2)
        )
        assert graph_repo.find_graph().get_entity_spot(
            EntityId.create(1)
        ) == SpotId.create(2)


class TestTravelStageOnArrival:
    """``#404`` fix: travel 完了時に on_arrival コールバックが発火する。

    移動中 player の LLM ターンは ``_can_player_act`` で sleep するため、
    到着時に schedule_turn を打って起こす経路が必要。travel_stage が
    is_traveling=True → False の遷移を検知して on_arrival を呼ぶ。
    """

    def test_calls_on_arrival(self) -> None:
        """travel が at_rest に遷移した tick で on_arrival(player_id) が来る。"""
        graph = _line_graph_three_spots(travel_ticks=1)
        graph_repo = InMemorySpotGraphRepository(graph)
        player_repo = InMemoryPlayerStatusRepository()
        player_repo.save(create_test_status_aggregate(player_id=1))

        svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
        ctx = _FixedContext(items=frozenset(), flags=frozenset())
        arrived: list[int] = []
        stage = SpotGraphTravelStageService(
            player_repo, svc, ctx,
            on_arrival=lambda pid: arrived.append(pid.value),
        )

        svc.start_travel_to_spot(PlayerId(1), SpotId.create(3), frozenset(), frozenset())
        stage.run(WorldTick(1))  # leg1 終了 (S1→S2)、まだ travel 中
        assert arrived == []
        stage.run(WorldTick(2))  # leg2 終了 (S2→S3)、at_rest に遷移
        assert arrived == [1]

    def test_does_not_call_tick_on_arrival(self) -> None:
        """is_traveling が継続している間はコールバックが鳴らない。"""
        graph = _line_graph_three_spots(travel_ticks=3)
        graph_repo = InMemorySpotGraphRepository(graph)
        player_repo = InMemoryPlayerStatusRepository()
        player_repo.save(create_test_status_aggregate(player_id=1))

        svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
        ctx = _FixedContext(items=frozenset(), flags=frozenset())
        arrived: list[int] = []
        stage = SpotGraphTravelStageService(
            player_repo, svc, ctx,
            on_arrival=lambda pid: arrived.append(pid.value),
        )

        svc.start_travel_to_spot(PlayerId(1), SpotId.create(3), frozenset(), frozenset())
        for t in range(1, 5):
            stage.run(WorldTick(t))
        assert arrived == []  # 6 tick 必要 (3+3) なのでまだ未到着

    def test_set_arrival_can_injected_later(self) -> None:
        """wiring の順序制約 (turn_trigger が travel_stage より後で構築される) を
        満たすため、コールバックは後付けで差し替えられる必要がある。"""
        graph = _line_graph_three_spots(travel_ticks=1)
        graph_repo = InMemorySpotGraphRepository(graph)
        player_repo = InMemoryPlayerStatusRepository()
        player_repo.save(create_test_status_aggregate(player_id=1))

        svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
        ctx = _FixedContext(items=frozenset(), flags=frozenset())
        stage = SpotGraphTravelStageService(player_repo, svc, ctx)
        arrived: list[int] = []
        stage.set_on_arrival(lambda pid: arrived.append(pid.value))

        svc.start_travel_to_spot(PlayerId(1), SpotId.create(2), frozenset(), frozenset())
        stage.run(WorldTick(1))
        assert arrived == [1]

    def test_on_arrival_exception_does_not_fail_travel_stage(self) -> None:
        """コールバック失敗は他 player の advance を止めない (fail-safe)。"""
        graph = _line_graph_three_spots(travel_ticks=1)
        graph_repo = InMemorySpotGraphRepository(graph)
        player_repo = InMemoryPlayerStatusRepository()
        player_repo.save(create_test_status_aggregate(player_id=1))

        svc = SpotGraphMovementApplicationService(graph_repo, player_repo)
        ctx = _FixedContext(items=frozenset(), flags=frozenset())

        def boom(pid):
            raise RuntimeError("notify boom")

        stage = SpotGraphTravelStageService(player_repo, svc, ctx, on_arrival=boom)

        svc.start_travel_to_spot(PlayerId(1), SpotId.create(2), frozenset(), frozenset())
        # 例外を呑む (fail-safe) のでテストが通る
        stage.run(WorldTick(1))

        # 到着自体はちゃんと完了している (travel_stage の本体は走り切る)
        p = player_repo.find_by_id(PlayerId(1))
        assert p is not None
        assert p.spot_navigation_state is not None
        assert not p.spot_navigation_state.is_traveling
