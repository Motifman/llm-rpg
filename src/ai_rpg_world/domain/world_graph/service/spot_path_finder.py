"""スポットグラフ上の最短経路 next-hop を計算するドメインサービス。

multi-spot CHASE で「target が居る spot に向かう次の 1 hop」を求めるために
使う。passable フィルタ (鍵フラグ / 所持アイテム) を呼び出し側で組んで渡す
ことで、通行不能な接続を経由しないルートを返す。

戻り値は `ConnectionId` (= 1 hop の移動先を一意に指すグラフ辺)。同一接続が
重複登録されることは前提に無いため、ID で `move_monster` に渡せる。

実装方針:
- BFS で from_spot から target_spot へ最短経路を探索
- 経路の先頭の接続を返す
- target に到達不可 / from_spot==target_spot なら None
- BFS の隣接展開時に passable フィルタを適用するため、通行不能な経路は
  完全に「無いもの」として扱われる
"""

from __future__ import annotations

from collections import deque
from typing import Callable, Dict, Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId


# 接続を通行可能かどうかを判定する callable。BFS の隣接展開で使う。
ConnectionPassableFilter = Callable[[SpotConnection], bool]


def find_next_hop(
    graph: SpotGraphAggregate,
    from_spot: SpotId,
    target_spot: SpotId,
    is_passable: ConnectionPassableFilter,
    *,
    max_distance: Optional[int] = None,
) -> Optional[ConnectionId]:
    """`from_spot` から `target_spot` に向かう最短経路の最初の接続 ID を返す。

    - 同 spot (from == target) → None
    - 到達不可 → None
    - `max_distance` が指定されていてその hop 数を超える経路しかなければ None

    Args:
        graph: SpotGraphAggregate
        from_spot: 出発 spot
        target_spot: 目的地 spot
        is_passable: 接続が通行可能かを判定する関数 (鍵フラグ等を考慮)
        max_distance: 探索打ち切り hop 数。None なら無制限。
    """
    if from_spot == target_spot:
        return None

    # `predecessor[spot] = (came_from_spot, connection_used_to_arrive)`
    predecessor: Dict[SpotId, tuple[SpotId, ConnectionId]] = {}
    queue: deque[tuple[SpotId, int]] = deque([(from_spot, 0)])
    visited = {from_spot}

    while queue:
        current, depth = queue.popleft()
        if max_distance is not None and depth >= max_distance:
            continue
        # 出力接続を ID 昇順に展開して再現性を確保する
        connections = sorted(
            graph.iter_outgoing_connections_from(current),
            key=lambda c: c.connection_id.value,
        )
        for conn in connections:
            if not is_passable(conn):
                continue
            nxt = conn.to_spot_id
            if nxt in visited:
                continue
            visited.add(nxt)
            predecessor[nxt] = (current, conn.connection_id)
            if nxt == target_spot:
                return _backtrack_first_hop(predecessor, from_spot, target_spot)
            queue.append((nxt, depth + 1))

    return None


def _backtrack_first_hop(
    predecessor: Dict[SpotId, tuple[SpotId, ConnectionId]],
    from_spot: SpotId,
    target_spot: SpotId,
) -> ConnectionId:
    """target からたどって最初の hop の接続 ID を返す。"""
    cursor = target_spot
    last_connection: Optional[ConnectionId] = None
    while cursor != from_spot:
        came_from, conn_id = predecessor[cursor]
        last_connection = conn_id
        cursor = came_from
    assert last_connection is not None  # from != target は呼び出し側でガード済み
    return last_connection
