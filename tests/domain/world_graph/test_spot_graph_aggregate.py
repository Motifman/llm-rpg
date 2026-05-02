from __future__ import annotations

import pytest

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionStateChangedEvent,
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionNotPassableException,
    DuplicateConnectionIdException,
    DuplicateSpotException,
    EntityNotAtSpotException,
    EntityNotInGraphException,
    SpotNotInGraphException,
    SpotPresenceInvariantException,
    UnknownConnectionException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


class TestSpotGraphAggregateFindConnection:
    def test_find_first_passable_connection_between(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="door",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
            )
        )
        c = g.find_first_passable_connection_between(SpotId.create(1), SpotId.create(2))
        assert c is not None
        assert c.connection_id == ConnectionId.create(1)
        assert g.find_first_passable_connection_between(SpotId.create(2), SpotId.create(1)) is None


class TestSpotGraphAggregateSpotsAndConnections:
    def test_duplicate_spot_raises(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        with pytest.raises(DuplicateSpotException):
            g.add_spot(_node(1))

    def test_connection_unknown_endpoint_raises(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        conn = SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="x",
            description="",
            travel_ticks=0,
            is_bidirectional=False,
        )
        with pytest.raises(SpotNotInGraphException):
            g.add_connection(conn)

    def test_bidirectional_requires_reverse_id(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        conn = SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="x",
            description="",
            travel_ticks=0,
            is_bidirectional=True,
        )
        with pytest.raises(ValueError):
            g.add_connection(conn)

    def test_bidirectional_adds_reverse_edge(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="x",
                description="",
                travel_ticks=0,
                is_bidirectional=True,
            ),
            reverse_connection_id=ConnectionId.create(2),
        )
        assert g.get_connection(ConnectionId.create(1)).to_spot_id == SpotId.create(2)
        assert g.get_connection(ConnectionId.create(2)).to_spot_id == SpotId.create(1)


class TestSpotGraphAggregatePlacement:
    def test_place_and_presence(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        e = EntityId.create(1)
        g.place_entity(e, SpotId.create(1))
        assert g.get_entity_spot(e) == SpotId.create(1)
        assert g.presence_at(SpotId.create(1)).is_present(e)

    def test_place_twice_raises(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        e = EntityId.create(1)
        g.place_entity(e, SpotId.create(1))
        with pytest.raises(SpotPresenceInvariantException):
            g.place_entity(e, SpotId.create(1))

    def test_place_emits_entered_event(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.place_entity(EntityId.create(1), SpotId.create(1))
        evs = g.get_events()
        assert len(evs) == 1
        assert isinstance(evs[0], EntityEnteredSpotEvent)
        assert evs[0].from_spot_id is None


class TestSpotGraphAggregateMove:
    @pytest.fixture
    def two_room_graph(self) -> SpotGraphAggregate:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="door",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
            )
        )
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.clear_events()
        return g

    def test_move_success_events_order(self, two_room_graph: SpotGraphAggregate):
        g = two_room_graph
        g.move_entity(EntityId.create(1), ConnectionId.create(1), frozenset(), frozenset())
        evs = g.get_events()
        assert len(evs) == 2
        assert isinstance(evs[0], EntityLeftSpotEvent)
        assert isinstance(evs[1], EntityEnteredSpotEvent)
        assert g.get_entity_spot(EntityId.create(1)) == SpotId.create(2)

    def test_move_wrong_origin_raises(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="door",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
            )
        )
        g.place_entity(EntityId.create(1), SpotId.create(2))
        with pytest.raises(EntityNotAtSpotException):
            g.move_entity(EntityId.create(1), ConnectionId.create(1), frozenset(), frozenset())

    def test_move_without_place_raises(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="door",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
            )
        )
        with pytest.raises(EntityNotInGraphException):
            g.move_entity(EntityId.create(1), ConnectionId.create(1), frozenset(), frozenset())

    def test_move_locked_connection_raises(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        key = ItemSpecId.create(5)
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="door",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage_conditions=[
                    PassageCondition(
                        condition_type=PassageConditionTypeEnum.ITEM_REQUIRED,
                        item_spec_id=key,
                        failure_message="鍵",
                    )
                ],
            )
        )
        g.place_entity(EntityId.create(1), SpotId.create(1))
        with pytest.raises(ConnectionNotPassableException):
            g.move_entity(EntityId.create(1), ConnectionId.create(1), frozenset(), frozenset())

    def test_move_with_key(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        key = ItemSpecId.create(5)
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="door",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                passage_conditions=[
                    PassageCondition(
                        condition_type=PassageConditionTypeEnum.ITEM_REQUIRED,
                        item_spec_id=key,
                    )
                ],
            )
        )
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.move_entity(EntityId.create(1), ConnectionId.create(1), frozenset({key}), frozenset())
        assert g.get_entity_spot(EntityId.create(1)) == SpotId.create(2)


class TestConnectionState:
    def test_set_passable_emits_once(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="d",
                description="",
                travel_ticks=0,
                is_bidirectional=False,
                is_passable=False,
            )
        )
        g.clear_events()
        g.set_connection_passable(ConnectionId.create(1), True)
        evs = g.get_events()
        assert len(evs) == 1
        assert isinstance(evs[0], ConnectionStateChangedEvent)
        assert evs[0].is_passable is True

    def test_set_passable_same_no_event(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="d",
                description="",
                travel_ticks=0,
                is_bidirectional=False,
                is_passable=True,
            )
        )
        g.clear_events()
        g.set_connection_passable(ConnectionId.create(1), True)
        assert g.get_events() == []

    def test_unknown_connection_raises(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        with pytest.raises(UnknownConnectionException):
            g.set_connection_passable(ConnectionId.create(99), True)


class TestConnectionRecords:
    def test_iter_connection_records_preserves_parallel_edges(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="stairs",
                description="",
                travel_ticks=3,
                is_bidirectional=True,
            ),
            reverse_connection_id=ConnectionId.create(2),
        )
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(3),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="vent",
                description="",
                travel_ticks=1,
                is_bidirectional=False,
                is_passable=False,
            )
        )
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(4),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="tunnel",
                description="",
                travel_ticks=0,
                is_bidirectional=True,
            ),
            reverse_connection_id=ConnectionId.create(5),
        )

        records = g.iter_connection_records()

        assert [(int(r.connection.connection_id.value), r.reverse_connection_id.value if r.reverse_connection_id else None) for r in records] == [
            (1, 2),
            (3, None),
            (4, 5),
        ]

    def test_iter_connection_records_detects_broken_reverse_pair(self):
        g = SpotGraphAggregate(
            graph_id=SpotGraphId.create(1),
            spots={SpotId.create(1): _node(1), SpotId.create(2): _node(2)},
            connections_by_id={
                ConnectionId.create(1): SpotConnection(
                    connection_id=ConnectionId.create(1),
                    from_spot_id=SpotId.create(1),
                    to_spot_id=SpotId.create(2),
                    name="door",
                    description="",
                    travel_ticks=1,
                    is_bidirectional=True,
                )
            },
            outgoing={SpotId.create(1): [ConnectionId.create(1)]},
            reverse_connections={ConnectionId.create(1): ConnectionId.create(2)},
        )

        with pytest.raises(SpotPresenceInvariantException, match="Reverse connection missing"):
            g.iter_connection_records()
