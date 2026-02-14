"""
インメモリのヘイトストア実装。
"""

from threading import Lock
from typing import Dict, Tuple

from ai_rpg_world.application.world.aggro_store import AggroStore
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class InMemoryAggroStore(AggroStore):
    """
    メモリ上で (spot_id, victim_id) -> { attacker_id -> 累積ヘイト } を保持する実装。
    スレッドセーフにするためロックを使用する。
    """

    def __init__(self) -> None:
        # (spot_id, victim_id) -> Dict[attacker_id, int]
        self._store: Dict[Tuple[SpotId, WorldObjectId], Dict[WorldObjectId, int]] = {}
        self._lock = Lock()

    def add_aggro(
        self,
        spot_id: SpotId,
        victim_id: WorldObjectId,
        attacker_id: WorldObjectId,
        amount: int = 1,
    ) -> None:
        if amount <= 0:
            raise ValueError(f"amount must be positive, got {amount}")
        key = (spot_id, victim_id)
        with self._lock:
            if key not in self._store:
                self._store[key] = {}
            current = self._store[key].get(attacker_id, 0)
            self._store[key][attacker_id] = current + amount

    def get_threat_by_attacker(
        self,
        spot_id: SpotId,
        attacker_id: WorldObjectId,
    ) -> Dict[WorldObjectId, int]:
        result: Dict[WorldObjectId, int] = {}
        with self._lock:
            for (sid, victim_id), by_attacker in self._store.items():
                if sid != spot_id:
                    continue
                if attacker_id in by_attacker and by_attacker[attacker_id] > 0:
                    result[victim_id] = by_attacker[attacker_id]
        return result
