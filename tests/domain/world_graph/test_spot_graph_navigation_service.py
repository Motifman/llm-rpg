from __future__ import annotations

import pytest

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum
from ai_rpg_world.domain.world_graph.service.spot_graph_navigation_service import SpotGraphNavigationService
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum


def _three_spot_line_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for i in range(1, 4):
        g.add_spot(
            SpotNode(
                spot_id=SpotId.create(i),
                name=f"S{i}",
                description="",
                category=SpotCategoryEnum.OTHER,
                parent_id=None,
            )
        )
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="a",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage_conditions=[],
            passage=Passage.open(sound_permeability=1.0),
        )
    )
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(2),
            from_spot_id=SpotId.create(2),
            to_spot_id=SpotId.create(3),
            name="b",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage_conditions=[],
            passage=Passage.open(sound_permeability=1.0),
        )
    )
    return g


class TestSpotGraphNavigationServiceRoute:
    def test_same_spot_returns_single_node(self):
        g = _three_spot_line_graph()
        nav = SpotGraphNavigationService()
        r = nav.calculate_route(g, SpotId.create(1), SpotId.create(1))
        assert r == [SpotId.create(1)]

    def test_shortest_path(self):
        g = _three_spot_line_graph()
        nav = SpotGraphNavigationService()
        r = nav.calculate_route(g, SpotId.create(1), SpotId.create(3))
        assert r == [SpotId.create(1), SpotId.create(2), SpotId.create(3)]

    def test_unreachable_returns_empty(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(
            SpotNode(
                spot_id=SpotId.create(1),
                name="A",
                description="",
                category=SpotCategoryEnum.OTHER,
                parent_id=None,
            )
        )
        g.add_spot(
            SpotNode(
                spot_id=SpotId.create(2),
                name="B",
                description="",
                category=SpotCategoryEnum.OTHER,
                parent_id=None,
            )
        )
        nav = SpotGraphNavigationService()
        assert nav.calculate_route(g, SpotId.create(1), SpotId.create(2)) == []

    def test_unknown_spot_returns_empty(self):
        g = _three_spot_line_graph()
        nav = SpotGraphNavigationService()
        assert nav.calculate_route(g, SpotId.create(1), SpotId.create(99)) == []

    def test_respects_closed_edge(self):
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        for i in (1, 2):
            g.add_spot(
                SpotNode(
                    spot_id=SpotId.create(i),
                    name=str(i),
                    description="",
                    category=SpotCategoryEnum.OTHER,
                    parent_id=None,
                )
            )
        g.add_connection(
            SpotConnection(
                connection_id=ConnectionId.create(1),
                from_spot_id=SpotId.create(1),
                to_spot_id=SpotId.create(2),
                name="x",
                description="",
                travel_ticks=0,
                is_bidirectional=False,
                passage_conditions=[],
            passage=Passage.door(DoorStateEnum.LOCKED, sound_permeability=1.0),
            )
        )
        nav = SpotGraphNavigationService()
        assert nav.calculate_route(g, SpotId.create(1), SpotId.create(2)) == []


class TestSpotGraphNavigationServiceCanPass:
    def test_blocked_connection(self):
        c = SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="x",
            description="",
            travel_ticks=0,
            is_bidirectional=False,
            passage=Passage.door(DoorStateEnum.LOCKED),
        )
        nav = SpotGraphNavigationService()
        ok, msg = nav.can_pass(c, frozenset(), frozenset())
        assert ok is False
        assert msg is not None

    def test_always_condition(self):
        c = SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="x",
            description="",
            travel_ticks=0,
            is_bidirectional=False,
            passage_conditions=[
                PassageCondition(condition_type=PassageConditionTypeEnum.ALWAYS)
            ],
        )
        nav = SpotGraphNavigationService()
        ok, msg = nav.can_pass(c, frozenset(), frozenset())
        assert ok is True
        assert msg is None

    def test_item_required_ok(self):
        spec = ItemSpecId.create(10)
        c = SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="x",
            description="",
            travel_ticks=0,
            is_bidirectional=False,
            passage_conditions=[
                PassageCondition(
                    condition_type=PassageConditionTypeEnum.ITEM_REQUIRED,
                    item_spec_id=spec,
                    failure_message="鍵が必要",
                )
            ],
        )
        nav = SpotGraphNavigationService()
        ok, msg = nav.can_pass(c, frozenset({spec}), frozenset())
        assert ok is True

    def test_item_required_fail(self):
        spec = ItemSpecId.create(10)
        c = SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="x",
            description="",
            travel_ticks=0,
            is_bidirectional=False,
            passage_conditions=[
                PassageCondition(
                    condition_type=PassageConditionTypeEnum.ITEM_REQUIRED,
                    item_spec_id=spec,
                    failure_message="鍵が必要",
                )
            ],
        )
        nav = SpotGraphNavigationService()
        ok, msg = nav.can_pass(c, frozenset(), frozenset())
        assert ok is False
        assert "鍵が必要" in (msg or "")

    def test_flag_set(self):
        c = SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="x",
            description="",
            travel_ticks=0,
            is_bidirectional=False,
            passage_conditions=[
                PassageCondition(
                    condition_type=PassageConditionTypeEnum.FLAG_SET,
                    flag_name="door_open",
                )
            ],
        )
        nav = SpotGraphNavigationService()
        assert nav.can_pass(c, frozenset(), frozenset({"door_open"}))[0] is True
        assert nav.can_pass(c, frozenset(), frozenset())[0] is False
