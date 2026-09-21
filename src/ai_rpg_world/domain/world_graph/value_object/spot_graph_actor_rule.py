from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpotGraphActorRule:
    """Spot Graph 上の自律アクター移動ルール（最小版）。"""

    entity_id: int
    patrol_route_spot_ids: tuple[int, ...]
    move_every_ticks: int = 3
    triggered_by_flag: str | None = None
    chases_player: bool = False
