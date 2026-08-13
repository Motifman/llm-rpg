"""区画ごとの在室数を、用途ごとの範囲を混ぜずに集計する。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


class SpotOccupancyScope(str, Enum):
    """同じ「人数」でも、何を一人と数えるかを明示する。"""

    MEETING_ELIGIBLE_PLAYERS = "meeting_eligible_players"
    LIVING_PLAYERS_AND_FALLEN_BODIES = "living_players_and_fallen_bodies"


@dataclass(frozen=True)
class SpotOccupancy:
    spot_id: str
    spot_name: str
    occupant_count: int


def collect_spot_occupancy(
    *,
    graph: Any,
    player_ids: Iterable[Any],
    player_life_query: Any,
    scope: SpotOccupancyScope,
    fallen_body_registry: Any | None = None,
) -> tuple[SpotOccupancy, ...]:
    """全区画を宣言順に返し、無人室も 0 として残す。

    社会密度の trace は会議に参加できる者だけを数える。位置表示盤は同じ
    生存者集計に遺体を足す。本家の表示盤と同じく、反応が生者か遺体かは
    区別しない。幽霊の位置はどちらの範囲にも含めない。
    """
    nodes = graph.iter_spot_nodes()
    counts = {str(node.spot_id.value): 0 for node in nodes}
    for player_id in player_ids:
        if not player_life_query.can_vote(player_id):
            continue
        try:
            spot_id = str(
                graph.get_entity_spot(EntityId.create(int(player_id))).value
            )
        except Exception:
            continue
        if spot_id in counts:
            counts[spot_id] += 1

    if scope is SpotOccupancyScope.LIVING_PLAYERS_AND_FALLEN_BODIES:
        if fallen_body_registry is None:
            raise ValueError("遺体を含む在室数には FallenBodyRegistry が必要です。")
        for body in fallen_body_registry.snapshot().values():
            spot_id = str(body.spot_id.value)
            if spot_id in counts:
                counts[spot_id] += 1

    return tuple(
        SpotOccupancy(
            spot_id=str(node.spot_id.value),
            spot_name=node.name,
            occupant_count=counts[str(node.spot_id.value)],
        )
        for node in nodes
    )


def format_room_occupancy_display(entries: Iterable[SpotOccupancy]) -> str:
    """名前を含めず、区画名と反応数だけを世界内の表示文へ整える。"""
    lines = ["所内位置表示盤には、各区画の反応数だけが表示されている。"]
    lines.extend(f"- {entry.spot_name}: {entry.occupant_count} 人" for entry in entries)
    return "\n".join(lines)


__all__ = [
    "SpotOccupancy",
    "SpotOccupancyScope",
    "collect_spot_occupancy",
    "format_room_occupancy_display",
]
