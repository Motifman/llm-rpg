"""ReactivePassageBindingStageService の毎 tick 評価挙動。

協力ギミック #15（役割分担リレー）の最小再現テスト：
A が制御室にいる間だけ、別の通路（DOOR.LOCKED）が DOOR.OPEN に切り替わる。
A が離れたら自動的に LOCKED に戻る。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.reactive_passage_binding_stage_service import (
    ReactivePassageBindingStageService,
)
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import (
    ReactivePassageBinding,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)


def _node(i: int, name: str = "") -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=name or f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _build_relay_graph() -> SpotGraphAggregate:
    """3 スポット (control_room=1, corridor=2, goal=3) と
    corridor→goal 間に LOCKED 扉を持つグラフ。"""
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1, "control_room"))
    g.add_spot(_node(2, "corridor"))
    g.add_spot(_node(3, "goal"))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SpotId.create(2),
            to_spot_id=SpotId.create(3),
            name="goal_door",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.door(DoorStateEnum.LOCKED),
        ),
    )
    g.clear_events()
    return g


def _build_stage(graph: SpotGraphAggregate, bindings):
    """評価器とステージを最小依存で組み立てる。"""
    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()

    # 必要な repository は HAS_ITEM/OBJECT_STATE では使わないので最小スタブで OK。
    class _NoopStatusRepo:
        def find_all(self):
            return []

    class _NoopInventoryRepo:
        def find_by_id(self, *_args, **_kwargs):
            return None

    class _NoopItemRepo:
        pass

    flag_state = MutableWorldFlagState()
    evaluator = ScenarioConditionEvaluator(
        world_flag_state=flag_state,
        spot_interior_repository=interior_repo,
        player_status_repository=_NoopStatusRepo(),
        player_inventory_repository=_NoopInventoryRepo(),
        item_repository=_NoopItemRepo(),
    )
    stage = ReactivePassageBindingStageService(
        bindings=bindings,
        spot_graph_repository=spot_graph_repo,
        condition_evaluator=evaluator,
    )
    return stage, spot_graph_repo, flag_state


def _player_at_control_room_binding() -> ReactivePassageBinding:
    return ReactivePassageBinding(
        target_connection_id=ConnectionId.create(10),
        predicate=ScenarioEventCondition(
            condition_type="PLAYER_AT_SPOT", spot_id=1,
        ),
        on_true_state="OPEN",
        on_false_state="LOCKED",
    )


class TestReactivePassageBindingStage:
    """ReactivePassageBindingStageService の predicate 評価と passage 切り替え。"""

    def test_no_change_when_no_bindings(self) -> None:
        """bindings が空ならグラフを保存しない（副作用なし）。"""
        graph = _build_relay_graph()
        stage, repo, _ = _build_stage(graph, bindings=())
        stage.run(WorldTick(1))
        # passage は LOCKED のまま
        assert repo.find_graph().get_connection(ConnectionId.create(10)).passage.state == "LOCKED"

    def test_predicate_true_transitions_to_on_true_state(self) -> None:
        """A が制御室に居れば扉が OPEN になる。"""
        graph = _build_relay_graph()
        graph.place_entity(EntityId.create(1), SpotId.create(1))  # A at control_room
        stage, repo, _ = _build_stage(graph, bindings=(_player_at_control_room_binding(),))
        stage.run(WorldTick(1))
        conn = repo.find_graph().get_connection(ConnectionId.create(10))
        assert conn.passage.state == "OPEN"
        assert conn.passage.traversable is True

    def test_predicate_false_transitions_to_on_false_state(self) -> None:
        """誰も制御室に居なければ扉は LOCKED のまま（既に LOCKED なので冪等）。"""
        graph = _build_relay_graph()
        # 制御室に誰も置かない
        stage, repo, _ = _build_stage(graph, bindings=(_player_at_control_room_binding(),))
        stage.run(WorldTick(1))
        conn = repo.find_graph().get_connection(ConnectionId.create(10))
        assert conn.passage.state == "LOCKED"

    def test_leave_control_room_closes_door_again(self) -> None:
        """制御室に居る → 離れる、で OPEN → LOCKED に戻る。"""
        graph = _build_relay_graph()
        eid = EntityId.create(1)
        graph.place_entity(eid, SpotId.create(1))
        stage, repo, _ = _build_stage(graph, bindings=(_player_at_control_room_binding(),))

        stage.run(WorldTick(1))
        graph_after_open = repo.find_graph()
        assert graph_after_open.get_connection(ConnectionId.create(10)).passage.state == "OPEN"

        # A を制御室から corridor 経由で出る経路を持たないので、テストでは
        # 別グラフで「A が居ない」状態を作って同じ binding を評価しなおす。
        graph_no_a = _build_relay_graph()
        # ControlRoom (cid=1) は LOCKED に戻った状態で初期化されているので、
        # OPEN にしてから run して LOCKED に戻ることを確認する。
        from dataclasses import replace
        cid = ConnectionId.create(10)
        old_conn = graph_no_a.get_connection(cid)
        graph_no_a.set_connection_passage(cid, replace(old_conn.passage, state="OPEN", traversable=True))
        repo.save(graph_no_a)

        stage.run(WorldTick(2))
        conn = repo.find_graph().get_connection(cid)
        assert conn.passage.state == "LOCKED"

    def test_idempotent_run_does_not_save_when_state_unchanged(self) -> None:
        """state がすでに目標と一致していれば save は呼ばれない（副作用最小化）。"""
        graph = _build_relay_graph()
        # 誰も居ない → predicate False → on_false_state="LOCKED"。既に LOCKED。
        stage, repo, _ = _build_stage(graph, bindings=(_player_at_control_room_binding(),))
        save_count = {"n": 0}
        original_save = repo.save

        def counting_save(g):
            save_count["n"] += 1
            return original_save(g)

        repo.save = counting_save  # type: ignore[assignment]
        stage.run(WorldTick(1))
        assert save_count["n"] == 0

    def test_composite_predicate_with_not_inverts_state(self) -> None:
        """NOT(PLAYER_AT_SPOT(control_room)) を述語にすると、誰も居ないとき OPEN になる。"""
        graph = _build_relay_graph()
        # 誰も control_room には居ない
        not_at_control = ScenarioEventCondition(
            condition_type="NOT",
            children=(
                ScenarioEventCondition(condition_type="PLAYER_AT_SPOT", spot_id=1),
            ),
        )
        binding = ReactivePassageBinding(
            target_connection_id=ConnectionId.create(10),
            predicate=not_at_control,
            on_true_state="OPEN",
            on_false_state="LOCKED",
        )
        stage, repo, _ = _build_stage(graph, bindings=(binding,))
        stage.run(WorldTick(1))
        # 誰も居ない → NOT True → on_true=OPEN
        assert repo.find_graph().get_connection(ConnectionId.create(10)).passage.state == "OPEN"

    def test_multiple_bindings_evaluated_independently(self) -> None:
        """複数 binding はそれぞれ独立に評価され、対象接続だけが影響を受ける。"""
        graph = _build_relay_graph()
        # 2 つ目の接続を追加（control_room→corridor の追加扉）
        graph.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(11),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="control_door",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage=Passage.door(DoorStateEnum.LOCKED),
            ),
        )
        graph.place_entity(EntityId.create(1), SpotId.create(1))

        b1 = _player_at_control_room_binding()  # cid=10 → OPEN
        b2 = ReactivePassageBinding(
            target_connection_id=ConnectionId.create(11),
            predicate=ScenarioEventCondition(condition_type="FLAG_SET", flag_name="never_set"),
            on_true_state="OPEN",
            on_false_state="LOCKED",
        )
        stage, repo, _ = _build_stage(graph, bindings=(b1, b2))
        stage.run(WorldTick(1))
        loaded = repo.find_graph()
        assert loaded.get_connection(ConnectionId.create(10)).passage.state == "OPEN"
        assert loaded.get_connection(ConnectionId.create(11)).passage.state == "LOCKED"


class TestReactivePassageBindingCause:
    """Issue #180: reactive_passage_binding 経由の state 変化は
    ConnectionStateChangedEvent.cause=REACTIVE で発火する。"""

    def test_reactive_change_emits_event_with_reactive_cause(self) -> None:
        """passage state を切り替えると cause=REACTIVE の event が graph に積まれる。"""
        from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
            PassageChangeCauseEnum,
        )
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            ConnectionStateChangedEvent,
        )

        graph = _build_relay_graph()
        # 誰も control_room に居ない → predicate=NOT(PLAYER_AT_SPOT control_room) は True
        not_at_control = ScenarioEventCondition(
            condition_type="NOT",
            children=(
                ScenarioEventCondition(
                    condition_type="PLAYER_AT_SPOT", spot_id=1,
                ),
            ),
        )
        # LOCKED 初期状態から OPEN に遷移する binding
        binding = ReactivePassageBinding(
            target_connection_id=ConnectionId.create(10),
            predicate=not_at_control,
            on_true_state="OPEN",
            on_false_state="LOCKED",
        )
        stage, repo, _ = _build_stage(graph, bindings=(binding,))
        stage.run(WorldTick(1))
        loaded = repo.find_graph()
        # traversable が変わったので event が積まれているはず
        events = [
            e for e in loaded.get_events()
            if isinstance(e, ConnectionStateChangedEvent)
        ]
        assert len(events) == 1
        assert events[0].cause == PassageChangeCauseEnum.REACTIVE
        assert events[0].traversable is True
