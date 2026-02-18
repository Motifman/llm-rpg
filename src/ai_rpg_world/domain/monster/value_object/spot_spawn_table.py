"""スポット単位のスポーンテーブル。出現しうるスロット一覧を保持する。"""

from dataclasses import dataclass
from typing import List

from ai_rpg_world.domain.monster.value_object.spawn_slot import SpawnSlot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


@dataclass(frozen=True)
class SpotSpawnTable:
    """このスポットで出現しうるスポーンスロットの一覧。設定の入れ替えが可能な骨格用。"""
    spot_id: SpotId
    slots: List[SpawnSlot]

    def __post_init__(self):
        if not isinstance(self.slots, list):
            raise TypeError("slots must be a list")
        for i, slot in enumerate(self.slots):
            if not isinstance(slot, SpawnSlot):
                raise TypeError(f"slots[{i}] must be SpawnSlot, got {type(slot).__name__}")
            if slot.spot_id != self.spot_id:
                raise ValueError(
                    f"slots[{i}].spot_id must match SpotSpawnTable.spot_id: "
                    f"{slot.spot_id} != {self.spot_id}"
                )
