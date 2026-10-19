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

    @pytest.mark.parametrize(
        "replacement,expected_kind,expected_state",
        [
            (Passage.wall(WallStateEnum.BROKEN), "WALL", "BROKEN"),
            (Passage.door(DoorStateEnum.OPEN), "DOOR", "OPEN"),
        ],
    )
    def test_replaces_passage(self, replacement: Passage, expected_kind: str, expected_state: str) -> None:
        """同種・別種の通路へ置換すると、形態・状態・通行可否・遮音値が変わる。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        g.set_connection_passage(ConnectionId.create(7), replacement)
        conn = g.get_connection(ConnectionId.create(7))
        assert conn.passage.kind.value == expected_kind
        assert conn.passage.state == expected_state
        assert conn.passage.traversable is True
        assert conn.passage.sound_permeability == pytest.approx(1.0)

    def test_emits_state_changed_event_when_passability_flips(self) -> None:
        """通行可否が変化したときだけ ConnectionStateChangedEvent が発火する。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        g.set_connection_passage(ConnectionId.create(7), Passage.wall(WallStateEnum.BROKEN))
        events = [e for e in g.get_events() if isinstance(e, ConnectionStateChangedEvent)]
        assert len(events) == 1
        assert events[0].traversable is True

    def test_no_event_when_passability_unchanged(self) -> None:
        """INTACTからCRACKEDへ実状態と遮音値は変わるが、通行変化の通知は出ない。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        g.set_connection_passage(ConnectionId.create(7), Passage.wall(WallStateEnum.CRACKED))
        passage = g.get_connection(ConnectionId.create(7)).passage
        assert passage.state == "CRACKED"
        assert passage.traversable is False
        assert passage.sound_permeability == pytest.approx(0.4)
        events = [e for e in g.get_events() if isinstance(e, ConnectionStateChangedEvent)]
        assert events == []


class TestSetConnectionPassageState:
    """SpotGraphAggregate.set_connection_passage_state の挙動。"""

    def test_transitions_state_keeping_kind(self) -> None:
        """同 kind を維持したまま state だけ遷移できる。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        g.set_connection_passage_state(ConnectionId.create(7), "BROKEN")
        conn = g.get_connection(ConnectionId.create(7))
        assert conn.passage.kind.value == "WALL"
        assert conn.passage.state == "BROKEN"

    @pytest.mark.parametrize(
        "new_state,overrides,expected_traversable",
        [
            ("CRACKED", {}, False),
            ("CRACKED", {"traversable_override": True}, True),
            ("BROKEN", {"traversable_override": False}, False),
        ],
    )
    def test_overrides_apply_to_transitioned_passage(
        self,
        new_state: str,
        overrides: dict[str, bool],
        expected_traversable: bool,
    ) -> None:
        """音の上書きと、未指定・真・偽の通行上書きを状態遷移へ反映する。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        g.set_connection_passage_state(
            ConnectionId.create(7),
            new_state,
            sound_permeability_override=0.55,
            **overrides,
        )
        conn = g.get_connection(ConnectionId.create(7))
        assert conn.passage.state == new_state
        assert conn.passage.traversable is expected_traversable
        assert conn.passage.sound_permeability == pytest.approx(0.55)

    def test_rejects_state_of_different_kind(self) -> None:
        """別 kind の state を渡すと PassageValidationException を投げる。"""
        g = _graph_with_wall_connection(WallStateEnum.INTACT)
        with pytest.raises(PassageValidationException):
            g.set_connection_passage_state(ConnectionId.create(7), "LOCKED")

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
        assert conn.passage.traversable is True
        assert conn.passage.state == "OPEN"
