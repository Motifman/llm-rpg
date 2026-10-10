"""移動の予約の後に区間の通路が閉じたとき、例外にせずその場で移動を取りやめることを保証する (#1559)。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from tests.domain.player.aggregate.test_player_status_aggregate import create_test_status_aggregate
from tests.support.trace_recorders import CollectingTraceRecorder

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
    SpotTravelBlocked,
    SpotTravelBlockedReason,
)
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
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.passage_kind import (
    BarrierStateEnum,
    DoorStateEnum,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)

_PLAYER = PlayerId(1)
_ENTITY = EntityId.create(1)
_S1, _S2, _S3 = SpotId.create(1), SpotId.create(2), SpotId.create(3)
_C1, _C2 = ConnectionId.create(1), ConnectionId.create(2)


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _connection(
    cid: ConnectionId,
    a: SpotId,
    b: SpotId,
    *,
    name: str,
    ticks: int,
    passage: Passage,
    conditions: list[PassageCondition] | None = None,
) -> SpotConnection:
    return SpotConnection(
        connection_id=cid,
        from_spot_id=a,
        to_spot_id=b,
        name=name,
        description="",
        travel_ticks=ticks,
        is_bidirectional=False,
        passage_conditions=conditions or [],
        passage=passage,
    )


def _graph(*connections: SpotConnection) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for i in (1, 2, 3):
        g.add_spot(_node(i))
    for c in connections:
        g.add_connection(c)
    g.place_entity(_ENTITY, _S1)
    g.clear_events()
    return g


class _DirectScopeFactory:
    def __init__(self, graph_repository, player_status_repository) -> None:
        self._repositories = SimpleNamespace(
            spot_graph=graph_repository,
            player_statuses=player_status_repository,
        )

    @contextmanager
    def create(self):
        yield SimpleNamespace(
            repositories=self._repositories,
            collect_all=lambda _events: None,
        )


@dataclass
class _Context:
    flags: frozenset[str] = frozenset()

    def owned_item_spec_ids_for(self, player_id: PlayerId) -> frozenset[ItemSpecId]:
        del player_id
        return frozenset()

    def world_flags(self) -> frozenset[str]:
        return self.flags


class _World:
    """移動サービスと travel stage を 1 人分組み立てる。"""

    def __init__(self, graph: SpotGraphAggregate, *, departed: bool = False) -> None:
        self.graph_repo = InMemorySpotGraphRepository(graph)
        self.player_repo = InMemoryPlayerStatusRepository()
        self.player_repo.save(create_test_status_aggregate(player_id=1))
        self.departed_store = DepartedPositionStore()
        if departed:
            self.departed_store.place(_PLAYER, _S1)
        self.service = SpotGraphMovementApplicationService(
            self.graph_repo,
            self.player_repo,
            departed_position_store=self.departed_store,
            player_perception_policy=SimpleNamespace(  # type: ignore[arg-type]
                is_departed=lambda _pid: departed
            ),
            command_scope_factory=_DirectScopeFactory(self.graph_repo, self.player_repo),
        )
        self.context = _Context()
        self.arrived: list[PlayerId] = []
        self.blocked: list[tuple[PlayerId, SpotTravelBlocked]] = []
        self.committed: list[PlayerId] = []
        self.stage = SpotGraphTravelStageService(
            self.player_repo,
            self.service,
            self.context,
            on_arrival=self.arrived.append,
            on_travel_tick_committed=self.committed.append,
        )
        self.stage.add_blocked_observer(
            lambda pid, blocked: self.blocked.append((pid, blocked))
        )

    def start(self, destination: SpotId) -> None:
        self.service.start_travel_to_spot(_PLAYER, destination, frozenset(), frozenset())

    def close(self, cid: ConnectionId, passage: Passage) -> None:
        graph = self.graph_repo.find_graph()
        graph.set_connection_passage(cid, passage)
        graph.clear_events()
        self.graph_repo.save(graph)

    def nav(self):
        status = self.player_repo.find_by_id(_PLAYER)
        assert status is not None
        return status.spot_navigation_state

    def spot(self) -> SpotId:
        return self.graph_repo.find_graph().get_entity_spot(_ENTITY)


def _door_world() -> _World:
    return _World(
        _graph(
            _connection(
                _C1, _S1, _S2, name="防火扉", ticks=2, passage=Passage.door(DoorStateEnum.OPEN)
            )
        )
    )


class TestPassageClosedMidTravel:
    """2 tick の区間の途中で通路が閉じたとき、出発した場所で移動が止まることを保証する。"""

    def test_locked_door_stops_travel_at_origin_without_exception(self) -> None:
        """扉の区間を移動中に扉が LOCKED になると、渡る tick に例外を出さず、本人は出発した場所で止まる。"""
        world = _door_world()
        world.start(_S2)
        world.stage.run(WorldTick(1))
        world.close(_C1, Passage.door(DoorStateEnum.LOCKED))

        world.stage.run(WorldTick(2))

        assert world.spot() == _S1
        nav = world.nav()
        assert nav is not None
        assert not nav.is_traveling
        assert nav.current_spot_id == _S1

    def test_locked_door_reports_the_connection_and_why(self) -> None:
        """止まったことは、閉じた通路の名前・種類・状態と、区間の両端・最終の行き先とともに止まった観察者へ 1 回だけ届く。"""
        world = _door_world()
        world.start(_S2)
        world.stage.run(WorldTick(1))
        world.close(_C1, Passage.door(DoorStateEnum.LOCKED))

        world.stage.run(WorldTick(2))

        assert world.blocked == [
            (
                _PLAYER,
                SpotTravelBlocked(
                    connection_id=_C1,
                    connection_name="防火扉",
                    from_spot_id=_S1,
                    to_spot_id=_S2,
                    destination_spot_id=_S2,
                    passage_kind="DOOR",
                    passage_state="LOCKED",
                    reason=SpotTravelBlockedReason.PASSAGE_CLOSED,
                    condition_message=None,
                ),
            )
        ]

    def test_blocked_travel_does_not_notify_arrival(self) -> None:
        """止まったときは到着の観察者を呼ばない。その tick の移動は確定済みとして数える。"""
        world = _door_world()
        world.start(_S2)
        world.stage.run(WorldTick(1))
        world.close(_C1, Passage.door(DoorStateEnum.LOCKED))

        world.stage.run(WorldTick(2))

        assert world.arrived == []
        assert world.committed == [_PLAYER, _PLAYER]

    def test_flooded_barrier_stops_travel_the_same_way(self) -> None:
        """浸水で障壁が ACTIVE になった区間も、例外にならず出発した場所で止まり、障壁の状態が届く。"""
        world = _World(
            _graph(
                _connection(
                    _C1,
                    _S1,
                    _S2,
                    name="下の道",
                    ticks=2,
                    passage=Passage.barrier(BarrierStateEnum.INACTIVE),
                )
            )
        )
        world.start(_S2)
        world.stage.run(WorldTick(1))
        world.close(_C1, Passage.barrier(BarrierStateEnum.ACTIVE))

        world.stage.run(WorldTick(2))

        assert world.spot() == _S1
        assert [(b.passage_kind, b.passage_state) for _, b in world.blocked] == [
            ("BARRIER", "ACTIVE")
        ]

    def test_failed_passage_condition_reports_the_scenario_message(self) -> None:
        """通行条件のフラグが移動中に消えると、理由は通行条件になり、シナリオの failure_message が届く。"""
        world = _World(
            _graph(
                _connection(
                    _C1,
                    _S1,
                    _S2,
                    name="吊り橋",
                    ticks=2,
                    passage=Passage.open(),
                    conditions=[
                        PassageCondition(
                            condition_type=PassageConditionTypeEnum.FLAG_SET,
                            flag_name="bridge_up",
                            failure_message="吊り橋が上がっている。",
                        )
                    ],
                )
            )
        )
        world.context.flags = frozenset({"bridge_up"})
        world.service.start_travel_to_spot(
            _PLAYER, _S2, frozenset(), frozenset({"bridge_up"})
        )
        world.stage.run(WorldTick(1))
        world.context.flags = frozenset()

        world.stage.run(WorldTick(2))

        assert world.spot() == _S1
        assert [(b.reason, b.condition_message) for _, b in world.blocked] == [
            (SpotTravelBlockedReason.PASSAGE_CONDITION, "吊り橋が上がっている。")
        ]

    def test_tick_after_blocked_travel_neither_notifies_nor_counts_travel(self) -> None:
        """止まった次の tick には、止まった通知も到着の通知も移動の計測も起きない (同じ区間を踏み直さない)。"""
        world = _door_world()
        world.start(_S2)
        world.stage.run(WorldTick(1))
        world.close(_C1, Passage.door(DoorStateEnum.LOCKED))
        world.stage.run(WorldTick(2))

        world.stage.run(WorldTick(3))

        assert len(world.blocked) == 1
        assert world.arrived == []
        assert world.committed == [_PLAYER, _PLAYER]
        assert world.spot() == _S1

    def test_can_travel_again_after_the_door_reopens(self) -> None:
        """止まった後に扉が開けば、同じ行き先への移動をもう一度始めて到着でき、止まった通知は増えない。"""
        world = _door_world()
        world.start(_S2)
        world.stage.run(WorldTick(1))
        world.close(_C1, Passage.door(DoorStateEnum.LOCKED))
        world.stage.run(WorldTick(2))
        world.close(_C1, Passage.door(DoorStateEnum.OPEN))

        world.start(_S2)
        world.stage.run(WorldTick(3))
        world.stage.run(WorldTick(4))

        assert world.spot() == _S2
        assert world.arrived == [_PLAYER]
        assert len(world.blocked) == 1


class TestPassageClosedOnLaterLeg:
    """複数の区間を 1 tick に渡る経路で、閉じた区間の手前で止まることを保証する。"""

    def test_stops_before_the_closed_second_leg(self) -> None:
        """1 区間目 (1 tick) と 2 区間目 (0 tick) を同じ tick に渡る経路で 2 区間目が閉じていると、1 区間目は渡り、その先で止まる。"""
        world = _World(
            _graph(
                _connection(_C1, _S1, _S2, name="a", ticks=1, passage=Passage.open()),
                _connection(
                    _C2, _S2, _S3, name="扉", ticks=0, passage=Passage.door(DoorStateEnum.OPEN)
                ),
            )
        )
        world.start(_S3)
        world.close(_C2, Passage.door(DoorStateEnum.LOCKED))

        world.stage.run(WorldTick(1))

        assert world.spot() == _S2
        nav = world.nav()
        assert nav is not None
        assert not nav.is_traveling
        assert nav.current_spot_id == _S2
        assert nav.route == ()
        assert world.arrived == []
        assert world.committed == [_PLAYER]
        assert [
            (b.connection_id, b.from_spot_id, b.to_spot_id, b.destination_spot_id)
            for _, b in world.blocked
        ] == [(_C2, _S2, _S3, _S3)]


    def test_closed_first_leg_stops_at_origin_and_reports_once(self) -> None:
        """2 区間の経路で両方の区間が閉じていても、止まるのは 1 区間目の手前で、通知は 1 回だけ、行き先は最終の場所になる。"""
        world = _World(
            _graph(
                _connection(
                    _C1, _S1, _S2, name="扉", ticks=0, passage=Passage.door(DoorStateEnum.OPEN)
                ),
                _connection(
                    _C2, _S2, _S3, name="奥の扉", ticks=0, passage=Passage.door(DoorStateEnum.OPEN)
                ),
            )
        )
        world.start(_S3)
        world.close(_C1, Passage.door(DoorStateEnum.LOCKED))
        world.close(_C2, Passage.door(DoorStateEnum.LOCKED))

        world.stage.run(WorldTick(1))

        assert world.spot() == _S1
        assert [
            (b.connection_id, b.from_spot_id, b.to_spot_id, b.destination_spot_id)
            for _, b in world.blocked
        ] == [(_C1, _S1, _S2, _S3)]


class TestDepartedTravelerBlocked:
    """去った主体 (幽霊) の経路でも、閉じた通路で例外にならず止まることを保証する。"""

    def test_departed_traveler_stays_at_origin(self) -> None:
        """幽霊が扉の区間を移動中に扉が LOCKED になると、例外を出さず、幽霊の位置は出発した場所のまま止まる。"""
        world = _World(
            _graph(
                _connection(
                    _C1, _S1, _S2, name="防火扉", ticks=2, passage=Passage.door(DoorStateEnum.OPEN)
                )
            ),
            departed=True,
        )
        world.start(_S2)
        world.stage.run(WorldTick(1))
        world.close(_C1, Passage.door(DoorStateEnum.LOCKED))

        world.stage.run(WorldTick(2))

        assert world.departed_store.find(_PLAYER) == _S1
        nav = world.nav()
        assert nav is not None
        assert not nav.is_traveling
        assert [b.connection_name for _, b in world.blocked] == ["防火扉"]


class TestBlockedObserverFailure:
    """止まった観察者が失敗しても、移動の取りやめと残りの観察者は失われないことを保証する。"""

    def test_failing_observer_does_not_undo_the_stop_or_skip_later_observers(self) -> None:
        """isolate で先に足した観察者が例外を投げても travel stage は例外を出さず、後の観察者にも届き、本人は止まったままで、失敗は travel.blocked_observer として trace に残る。"""
        world = _door_world()

        def _fail(_pid, _blocked) -> None:
            raise RuntimeError("observer failed")

        later: list[PlayerId] = []
        recorder = CollectingTraceRecorder()
        world.stage = SpotGraphTravelStageService(
            world.player_repo,
            world.service,
            world.context,
            failure_isolator=WorldTickFailureIsolator(
                policy=WorldTickFailurePolicy.ISOLATE,
                trace_recorder_provider=lambda: recorder,
            ),
        )
        world.stage.add_blocked_observer(_fail)
        world.stage.add_blocked_observer(lambda pid, _b: later.append(pid))
        world.start(_S2)
        world.stage.run(WorldTick(1))
        world.close(_C1, Passage.door(DoorStateEnum.LOCKED))

        world.stage.run(WorldTick(2))

        assert later == [_PLAYER]
        nav = world.nav()
        assert nav is not None
        assert not nav.is_traveling
        assert [
            e.payload["stage"] for e in recorder.of_kind(TraceEventKind.WORLD_TICK_UNIT_FAILED)
        ] == ["travel.blocked_observer"]


class TestPostCommitFailureAfterBlocked:
    """確定後の後処理が失敗して結果が返らないとき、行き先に着いていなければ到着として通知しないことを保証する。"""

    @staticmethod
    def _stage_with_post_commit_failure(settle_at: SpotId):
        player_repo = InMemoryPlayerStatusRepository()
        status = create_test_status_aggregate(player_id=1)
        status.set_spot_navigation_state(
            PlayerSpotNavigationState.begin_travel(
                route=(_S1, _S2),
                leg_connection_ids=(_C1,),
                leg_travel_ticks=(1,),
            )
        )
        player_repo.save(status)

        class _Movement:
            def advance_spot_travel_one_tick(self, player_id, items, flags):
                del items, flags
                current = player_repo.find_by_id(player_id)
                assert current is not None
                current.set_spot_navigation_state(PlayerSpotNavigationState.at_rest(settle_at))
                player_repo.save(current)
                raise CommandPostCommitException(cleanup_error=RuntimeError("cleanup failed"))

        arrived: list[PlayerId] = []
        stage = SpotGraphTravelStageService(
            player_repo,
            _Movement(),  # type: ignore[arg-type]
            _Context(),
            on_arrival=arrived.append,
        )
        return stage, arrived

    def test_abandoned_travel_is_not_reported_as_arrival(self) -> None:
        """取りやめて出発した場所で止まったまま後処理が失敗すると、例外は上がるが到着の観察者は呼ばれない。"""
        stage, arrived = self._stage_with_post_commit_failure(settle_at=_S1)

        with pytest.raises(CommandPostCommitException):
            stage.run(WorldTick(1))

        assert arrived == []

    def test_real_arrival_is_still_reported(self) -> None:
        """行き先に着いてから後処理が失敗したときは、これまでどおり到着の観察者が呼ばれる。"""
        stage, arrived = self._stage_with_post_commit_failure(settle_at=_S2)

        with pytest.raises(CommandPostCommitException):
            stage.run(WorldTick(1))

        assert arrived == [_PLAYER]
