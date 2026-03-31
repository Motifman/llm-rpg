"""スポットグラフ用 SQLite への初期データ投入（ワールド初期化）。"""

from __future__ import annotations

import sqlite3
from typing import Mapping, Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.infrastructure.repository.spot_graph_sqlite_schema import init_spot_graph_schema
from ai_rpg_world.infrastructure.repository.sqlite_spot_graph_repository import SqliteSpotGraphRepository
from ai_rpg_world.infrastructure.repository.sqlite_spot_interior_repository import SqliteSpotInteriorRepository


def seed_spot_graph_to_sqlite(
    connection: sqlite3.Connection,
    graph: SpotGraphAggregate,
    interiors: Optional[Mapping[SpotId, SpotInterior]] = None,
) -> None:
    """スポットグラフ集約と任意のスポット内部を SQLite に保存し、コミットする。

    Args:
        connection: sqlite3 接続（:memory: 可）
        graph: 永続化する SpotGraphAggregate
        interiors: スポット ID ごとの SpotInterior（ノードに埋め込まない運用向け）
    """
    init_spot_graph_schema(connection)
    connection.execute("BEGIN")
    try:
        graph_repo = SqliteSpotGraphRepository.for_shared_unit_of_work(connection)
        interior_repo = SqliteSpotInteriorRepository.for_shared_unit_of_work(connection)
        graph_repo.save(graph)
        for spot_id, interior in (interiors or {}).items():
            interior_repo.save(spot_id, interior)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


__all__ = ["seed_spot_graph_to_sqlite"]
