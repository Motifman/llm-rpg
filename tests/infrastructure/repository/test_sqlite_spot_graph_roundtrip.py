"""スポットグラフ SQLite 永続化のラウンドトリップ検証。"""

from __future__ import annotations

import json
import sqlite3

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import SpotNotInGraphException
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.repository.spot_graph_persistence_exceptions import (
    SpotGraphConnectionRecordInvariantError,
    SpotGraphSnapshotNotInitializedError,
    SpotGraphStateDecodeError,
    UnsupportedSpotGraphAggregateSchemaError,
    UnsupportedSpotInteriorSchemaError,
)
from ai_rpg_world.infrastructure.repository.spot_graph_sqlite_seed import seed_spot_graph_to_sqlite
from ai_rpg_world.infrastructure.repository.sqlite_spot_graph_repository import SqliteSpotGraphRepository
from ai_rpg_world.infrastructure.repository.sqlite_spot_interior_repository import SqliteSpotInteriorRepository
from ai_rpg_world.infrastructure.repository.sqlite_world_graph_state_codec import (
    dumps_spot_graph_aggregate,
    loads_spot_graph_aggregate,
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


def _parallel_edge_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(SpotGraphId.create(2))
    g.add_spot(_node(1))
    g.add_spot(_node(2))
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="stairs",
            description="slow",
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
            description="oneway",
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
            description="fast",
            travel_ticks=0,
            is_bidirectional=True,
        ),
        reverse_connection_id=ConnectionId.create(5),
    )
    g.place_entity(EntityId.create(9), SpotId.create(1))
    g.clear_events()
    return g


def _memory_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_sqlite_roundtrip_locked_door_graph_and_interior() -> None:
    graph = _graph_with_locked_connection()
    interior = _switch_interior()
    conn = _memory_connection()
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
    conn = _memory_connection()
    seed_spot_graph_to_sqlite(conn, graph, None)

    g_repo = SqliteSpotGraphRepository.for_standalone_connection(conn)
    loaded = g_repo.find_graph()
    assert spot_graph_aggregate_to_json_dict(loaded) == spot_graph_aggregate_to_json_dict(graph)


def test_sqlite_roundtrip_preserves_passage_field() -> None:
    """SpotConnection.passage が SQLite ラウンドトリップで保持される。"""
    from ai_rpg_world.domain.world_graph.enum.passage_kind import WallStateEnum
    from ai_rpg_world.domain.world_graph.value_object.passage import Passage

    g = SpotGraphAggregate.empty(SpotGraphId.create(99))
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
            passage=Passage.wall(WallStateEnum.CRACKED),
        ),
    )
    g.place_entity(EntityId.create(1), SpotId.create(1))
    g.clear_events()

    conn = _memory_connection()
    seed_spot_graph_to_sqlite(conn, g, None)
    loaded = SqliteSpotGraphRepository.for_standalone_connection(conn).find_graph()
    loaded_conn = loaded.get_connection(ConnectionId.create(7))
    assert loaded_conn.passage is not None
    assert loaded_conn.passage.kind.value == "WALL"
    assert loaded_conn.passage.state == "CRACKED"
    assert loaded_conn.is_passable is False
    assert loaded_conn.sound_permeability == pytest.approx(0.4)


def test_sqlite_roundtrip_parallel_edges_preserves_pairing() -> None:
    graph = _parallel_edge_graph()
    conn = _memory_connection()
    seed_spot_graph_to_sqlite(conn, graph, None)

    loaded = SqliteSpotGraphRepository.for_standalone_connection(conn).find_graph()

    assert spot_graph_aggregate_to_json_dict(loaded) == spot_graph_aggregate_to_json_dict(graph)


def test_find_graph_without_snapshot_raises_specific_exception() -> None:
    repo = SqliteSpotGraphRepository.for_standalone_connection(_memory_connection())
    with pytest.raises(SpotGraphSnapshotNotInitializedError):
        repo.find_graph()


def test_find_graph_invalid_json_raises_decode_error() -> None:
    conn = _memory_connection()
    repo = SqliteSpotGraphRepository.for_standalone_connection(conn)
    conn.execute("INSERT INTO spot_graph_snapshot (id, payload_json) VALUES (1, ?)", ("not json",))
    conn.commit()

    with pytest.raises(SpotGraphStateDecodeError):
        repo.find_graph()


def test_find_graph_unsupported_schema_raises() -> None:
    conn = _memory_connection()
    repo = SqliteSpotGraphRepository.for_standalone_connection(conn)
    payload = {"schema_version": 999, "graph_id": 1, "spots": [], "connection_records": [], "entity_spot": {}}
    conn.execute(
        "INSERT INTO spot_graph_snapshot (id, payload_json) VALUES (1, ?)",
        (json.dumps(payload),),
    )
    conn.commit()

    with pytest.raises(UnsupportedSpotGraphAggregateSchemaError):
        repo.find_graph()


def test_find_interior_invalid_json_raises_decode_error() -> None:
    conn = _memory_connection()
    repo = SqliteSpotInteriorRepository.for_standalone_connection(conn)
    conn.execute(
        "INSERT INTO spot_graph_interior (spot_id, payload_json) VALUES (?, ?)",
        (1, "not json"),
    )
    conn.commit()

    with pytest.raises(SpotGraphStateDecodeError):
        repo.find_by_spot_id(SpotId.create(1))


def test_find_interior_unsupported_schema_raises() -> None:
    conn = _memory_connection()
    repo = SqliteSpotInteriorRepository.for_standalone_connection(conn)
    conn.execute(
        "INSERT INTO spot_graph_interior (spot_id, payload_json) VALUES (?, ?)",
        (1, json.dumps({"schema_version": 999, "sub_locations": [], "objects": [], "ground_items": [], "discoverable_items": []})),
    )
    conn.commit()

    with pytest.raises(UnsupportedSpotInteriorSchemaError):
        repo.find_by_spot_id(SpotId.create(1))


def test_shared_uow_graph_repository_write_requires_transaction() -> None:
    repo = SqliteSpotGraphRepository.for_shared_unit_of_work(_memory_connection())
    with pytest.raises(RuntimeError, match="アクティブなトランザクション内"):
        repo.save(_bidirectional_graph())


def test_shared_uow_interior_repository_write_requires_transaction() -> None:
    repo = SqliteSpotInteriorRepository.for_shared_unit_of_work(_memory_connection())
    with pytest.raises(RuntimeError, match="アクティブなトランザクション内"):
        repo.save(SpotId.create(1), _switch_interior())


def test_seed_rejects_unknown_interior_spot_and_rolls_back() -> None:
    conn = _memory_connection()
    graph = _bidirectional_graph()

    with pytest.raises(SpotNotInGraphException):
        seed_spot_graph_to_sqlite(conn, graph, {SpotId.create(999): _switch_interior()})

    row = conn.execute("SELECT COUNT(*) FROM spot_graph_snapshot").fetchone()
    assert row is not None
    assert int(row[0]) == 0


def test_seed_rolls_back_when_interior_serialization_fails() -> None:
    conn = _memory_connection()
    graph = _bidirectional_graph()
    bad_interior = SpotInterior(
        sub_locations=(),
        objects=(
            SpotObject(
                object_id=SpotObjectId.create(1),
                name="Broken",
                description="",
                object_type=SpotObjectTypeEnum.OTHER,
                state={"broken": {1}},
                interactions=(),
            ),
        ),
        ground_items=(),
        discoverable_items=(),
    )

    with pytest.raises(TypeError):
        seed_spot_graph_to_sqlite(conn, graph, {SpotId.create(1): bad_interior})

    row = conn.execute("SELECT COUNT(*) FROM spot_graph_snapshot").fetchone()
    assert row is not None
    assert int(row[0]) == 0


def test_loads_spot_graph_aggregate_rejects_broken_bidirectional_record() -> None:
    payload = {
        "schema_version": 2,
        "graph_id": 1,
        "spots": [
            {"spot_id": 1, "name": "S1", "description": "d", "category": "OTHER", "parent_id": None},
            {"spot_id": 2, "name": "S2", "description": "d", "category": "OTHER", "parent_id": None},
        ],
        "connection_records": [
            {
                "kind": "bidirectional",
                "conn": {
                    "connection_id": 1,
                    "from_spot_id": 1,
                    "to_spot_id": 2,
                    "name": "door",
                    "description": "",
                    "travel_ticks": 1,
                    "is_bidirectional": True,
                    "passage_conditions": [],
                    "sound_permeability": 1.0,
                    "is_passable": True,
                },
            }
        ],
        "entity_spot": {},
    }

    with pytest.raises(SpotGraphConnectionRecordInvariantError):
        loads_spot_graph_aggregate(json.dumps(payload))


def test_dumps_spot_graph_aggregate_uses_explicit_pairing_for_parallel_edges() -> None:
    payload = json.loads(dumps_spot_graph_aggregate(_parallel_edge_graph()))
    bidirectional = [record for record in payload["connection_records"] if record["kind"] == "bidirectional"]

    assert len(bidirectional) == 2
    assert {(record["conn"]["connection_id"], record["reverse_connection_id"]) for record in bidirectional} == {
        (1, 2),
        (4, 5),
    }
