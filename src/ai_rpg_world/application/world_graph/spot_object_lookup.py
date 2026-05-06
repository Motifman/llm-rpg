"""SpotObject をスポットグラフ全体から検索する共通ヘルパ。

scenario_event_stage / scenario_condition_evaluator など、複数の
application 層サービスが「object_id からオブジェクトとオーナースポットを
逆引きしたい」要件を持つ。重複実装を避けるため module-level の純粋
関数として 1 箇所に置く。
"""

from __future__ import annotations

from typing import Optional, Tuple, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

if TYPE_CHECKING:
    from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
        SpotGraphAggregate,
    )


def find_owner_spot_id(
    object_id: SpotObjectId,
    graph: "SpotGraphAggregate",
    interior_repository: ISpotInteriorRepository,
) -> Optional[SpotId]:
    """object_id を含むスポットの ID を返す。見つからなければ None。"""
    for node in graph.iter_spot_nodes():
        interior = interior_repository.find_by_spot_id(node.spot_id)
        if interior is None:
            continue
        if interior.get_object(object_id) is not None:
            return node.spot_id
    return None


def find_object_in_graph(
    object_id: SpotObjectId,
    graph: "SpotGraphAggregate",
    interior_repository: ISpotInteriorRepository,
) -> Optional[SpotObject]:
    """object_id のオブジェクトを返す。見つからなければ None。"""
    owner = find_owner_spot_id(object_id, graph, interior_repository)
    if owner is None:
        return None
    interior = interior_repository.find_by_spot_id(owner)
    if interior is None:
        return None
    return interior.get_object(object_id)


def find_object_with_owner(
    object_id: SpotObjectId,
    graph: "SpotGraphAggregate",
    interior_repository: ISpotInteriorRepository,
) -> Tuple[Optional[SpotObject], Optional[SpotId]]:
    """object_id のオブジェクトとオーナースポット ID を一度に返す。"""
    owner = find_owner_spot_id(object_id, graph, interior_repository)
    if owner is None:
        return None, None
    interior = interior_repository.find_by_spot_id(owner)
    if interior is None:
        return None, owner
    return interior.get_object(object_id), owner
