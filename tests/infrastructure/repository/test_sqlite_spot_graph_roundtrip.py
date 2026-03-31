"""スポットグラフ SQLite 永続化のラウンドトリップ検証。"""

from __future__ import annotations

import sqlite3

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.repository.sqlite_spot_graph_repository import SqliteSpotGraphRepository
from ai_rpg_world.infrastructure.repository.sqlite_spot_interior_repository import SqliteSpotInteriorRepository
from ai_rpg_world.infrastructure.repository.sqlite_world_graph_state_codec import (
    spot_graph_aggregate_to_json_dict,
    spot_interior_to_json_dict,
)
from tests.application.world_graph.test_spot_graph_step4_integration import (
    _graph_with_locked_connection,
    _switch_interior,
)


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _bidirectional_graph() -> SpotGraphAggregate:
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
    g.place_entity(EntityId.create(1), SpotId.create(1))
    g.clear_events()
    return g


def test_sqlite_roundtrip_locked_door_graph_and_interior() -> None:
    graph = _graph_with_locked_connection()
    interior = _switch_interior()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    from ai_rpg_world.application.world_graph.spot_graph_world_seed import seed_spot_graph_to_sqlite

    seed_spot_graph_to_sqlite(conn, graph, {SpotId.create(1): interior})

    g_repo = SqliteSpotGraphRepository.for_standalone_connection(conn)
    i_repo = SqliteSpotInteriorRepository.for_standalone_connection(conn)

    loaded = g_repo.find_graph()
    loaded_interior = i_repo.find_by_spot_id(SpotId.create(1))
    assert loaded_interior is not None

    expected = spot_graph_aggregate_to_json_dict(graph)
    actual = spot_graph_aggregate_to_json_dict(loaded)
    assert actual == expected
    assert spot_interior_to_json_dict(loaded_interior) == spot_interior_to_json_dict(interior)


def test_sqlite_roundtrip_bidirectional() -> None:
    graph = _bidirectional_graph()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    from ai_rpg_world.application.world_graph.spot_graph_world_seed import seed_spot_graph_to_sqlite

    seed_spot_graph_to_sqlite(conn, graph, None)

    g_repo = SqliteSpotGraphRepository.for_standalone_connection(conn)
    loaded = g_repo.find_graph()
    assert spot_graph_aggregate_to_json_dict(loaded) == spot_graph_aggregate_to_json_dict(graph)
