"""スポットグラフ用 SQLite への初期データ投入。"""

from __future__ import annotations

import sqlite3
from typing import Mapping, Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import SpotNotInGraphException
from ai_rpg_world.infrastructure.repository.spot_graph_sqlite_schema import init_spot_graph_schema
from ai_rpg_world.infrastructure.repository.sqlite_spot_graph_repository import SqliteSpotGraphRepository
from ai_rpg_world.infrastructure.repository.sqlite_spot_interior_repository import SqliteSpotInteriorRepository


def seed_spot_graph_to_sqlite(
    connection: sqlite3.Connection,
    graph: SpotGraphAggregate,
    interiors: Optional[Mapping[SpotId, SpotInterior]] = None,
) -> None:
    """スポットグラフ集約と任意のスポット内部を SQLite に保存する。"""
    init_spot_graph_schema(connection)
    provided_interiors = dict(interiors or {})
    for spot_id in provided_interiors:
        if not graph.contains_spot(spot_id):
            raise SpotNotInGraphException(
                f"Cannot seed interior for unknown spot: {spot_id}"
            )

    started_without_transaction = not connection.in_transaction
    savepoint_name = "spot_graph_seed"
    if started_without_transaction:
        connection.execute("BEGIN")
    else:
        connection.execute(f"SAVEPOINT {savepoint_name}")

    try:
        graph_repo = SqliteSpotGraphRepository.for_shared_unit_of_work(connection)
        interior_repo = SqliteSpotInteriorRepository.for_shared_unit_of_work(connection)
        graph_repo.save(graph)
        for spot_id, interior in provided_interiors.items():
            interior_repo.save(spot_id, interior)
        if started_without_transaction:
            connection.commit()
        else:
            connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")
    except Exception:
        if started_without_transaction:
            if connection.in_transaction:
                connection.rollback()
        else:
            connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            connection.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        raise


__all__ = ["seed_spot_graph_to_sqlite"]
