"""SpotGraphAggregate.set_connection_passage / set_connection_passage_state の挙動テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.passage_kind import (
    DoorStateEnum,
    WallStateEnum,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionStateChangedEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionPassageMissingException,
    PassageValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _graph_with_wall_connection(wall_state: WallStateEnum = WallStateEnum.INTACT) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(7),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="教室間の壁",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.wall(wall_state),
        ),
    )
    g.clear_events()
    return g


class TestSetConnectionPassage:
    """SpotGraphAggregate.set_connection_passage の挙動。"""

    def test_replaces_passage_and_syncs_legacy_fields(self) -> None:
        """passage を置換すると is_passable / sound_permeability も同期される。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        new_passage = Passage.wall(WallStateEnum.BROKEN)
        g.set_connection_passage(ConnectionId.create(7), new_passage)
        conn = g.get_connection(ConnectionId.create(7))
        assert conn.passage is not None
        assert conn.passage.state == "BROKEN"
        assert conn.is_passable is True
        assert conn.sound_permeability == pytest.approx(1.0)

    def test_emits_state_changed_event_when_passability_flips(self) -> None:
        """通行可否が変化したときだけ ConnectionStateChangedEvent が発火する。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        g.set_connection_passage(
            ConnectionId.create(7), Passage.wall(WallStateEnum.BROKEN)
        )
        events = [e for e in g.get_events() if isinstance(e, ConnectionStateChangedEvent)]
        assert len(events) == 1
        assert events[0].is_passable is True

    def test_no_event_when_passability_unchanged(self) -> None:
        """通行可否が変わらない遷移（INTACT→CRACKED）ではイベントが出ない。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        g.set_connection_passage(
            ConnectionId.create(7), Passage.wall(WallStateEnum.CRACKED)
        )
        events = [e for e in g.get_events() if isinstance(e, ConnectionStateChangedEvent)]
        assert events == []


class TestSetConnectionPassageState:
    """SpotGraphAggregate.set_connection_passage_state の挙動。"""

    def test_transitions_state_keeping_kind(self) -> None:
        """同 kind を維持したまま state だけ遷移できる。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        g.set_connection_passage_state(ConnectionId.create(7), "BROKEN")
        conn = g.get_connection(ConnectionId.create(7))
        assert conn.passage is not None
        assert conn.passage.kind.value == "WALL"
        assert conn.passage.state == "BROKEN"

    def test_overrides_apply_to_transitioned_passage(self) -> None:
        """traversable / sound_permeability の override が遷移後の passage に反映される。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        g.set_connection_passage_state(
            ConnectionId.create(7),
            "CRACKED",
            sound_permeability_override=0.55,
        )
        conn = g.get_connection(ConnectionId.create(7))
        assert conn.sound_permeability == pytest.approx(0.55)

    def test_rejects_state_of_different_kind(self) -> None:
        """別 kind の state を渡すと PassageValidationException を投げる。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        with pytest.raises(PassageValidationException):
            g.set_connection_passage_state(ConnectionId.create(7), "LOCKED")

    def test_rejects_connection_without_passage(self) -> None:
        """passage を持たない接続では ConnectionPassageMissingException を投げる。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(2))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(8),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="legacy",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
            ),
        )
        with pytest.raises(ConnectionPassageMissingException):
            g.set_connection_passage_state(ConnectionId.create(8), "BROKEN")

    def test_door_locked_to_open_transition(self) -> None:
        """LOCKED 扉を OPEN へ遷移させると通行可になる。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(3))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(9),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="扉",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage=Passage.door(DoorStateEnum.LOCKED),
            ),
        )
        g.clear_events()
        g.set_connection_passage_state(ConnectionId.create(9), "OPEN")
        conn = g.get_connection(ConnectionId.create(9))
        assert conn.is_passable is True
        assert conn.passage is not None
        assert conn.passage.state == "OPEN"
