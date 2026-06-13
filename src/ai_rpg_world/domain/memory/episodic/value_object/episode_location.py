"""EpisodeLocation — エピソードが起きた場所 (タイル/スポット両対応)。

DDD 再編 (Issue #470 Phase 1 PR2): 元 ``application/llm/contracts/episodic_memory.py``
から domain に昇格。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class EpisodeLocation:
    """構造化された「どこで」（タイル／スポットグラフ双方を許容）。"""

    spot_id: int | None = None
    tile_area_ids: Tuple[int, ...] = ()
    sub_location_id: int | None = None
    x: int | None = None
    y: int | None = None
    z: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tile_area_ids, tuple):
            raise TypeError("tile_area_ids must be tuple[int, ...]")
        for idx, aid in enumerate(self.tile_area_ids):
            if not isinstance(aid, int):
                raise TypeError(f"tile_area_ids[{idx}] must be int")
        for name, val in (
            ("spot_id", self.spot_id),
            ("sub_location_id", self.sub_location_id),
            ("x", self.x),
            ("y", self.y),
            ("z", self.z),
        ):
            if val is not None and not isinstance(val, int):
                raise TypeError(f"{name} must be int or None")


__all__ = ["EpisodeLocation"]
