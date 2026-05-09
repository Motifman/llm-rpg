from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    MonsterPresenceInvariantException,
)


@dataclass(frozen=True)
class MonsterSpotPresence:
    """あるスポットに居るモンスター個体集合（不変）。

    プレイヤー/NPC を扱う SpotPresence とは独立に管理する。理由は
    (1) ライフサイクル (spawn / death / respawn) が異なる、
    (2) 観測導線で文体・visibility ルールを別に持たせたい、
    (3) 将来の生態系 tick で MonsterId をキーに直接索きたい、の 3 点。
    """

    spot_id: SpotId
    present_monster_ids: FrozenSet[MonsterId]

    def is_present(self, monster_id: MonsterId) -> bool:
        return monster_id in self.present_monster_ids

    def count(self) -> int:
        return len(self.present_monster_ids)

    def add(self, monster_id: MonsterId) -> "MonsterSpotPresence":
        if monster_id in self.present_monster_ids:
            raise MonsterPresenceInvariantException(
                f"Monster {monster_id} is already present at spot {self.spot_id}"
            )
        new_ids = set(self.present_monster_ids)
        new_ids.add(monster_id)
        return MonsterSpotPresence(self.spot_id, frozenset(new_ids))

    def remove(self, monster_id: MonsterId) -> "MonsterSpotPresence":
        if monster_id not in self.present_monster_ids:
            raise MonsterPresenceInvariantException(
                f"Monster {monster_id} is not present at spot {self.spot_id}"
            )
        new_ids = set(self.present_monster_ids)
        new_ids.remove(monster_id)
        return MonsterSpotPresence(self.spot_id, frozenset(new_ids))

    @staticmethod
    def empty(spot_id: SpotId) -> "MonsterSpotPresence":
        return MonsterSpotPresence(spot_id, frozenset())
