"""
インメモリのヘイトストア実装。
(amount, last_seen_tick) を保持し、取得時に AggroMemoryPolicy で忘却判定する。
"""

from threading import Lock
from typing import Dict, Optional, Tuple

from ai_rpg_world.application.world.aggro_store import AggroStore
from ai_rpg_world.domain.world.value_object.aggro_memory_policy import AggroMemoryPolicy
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class InMemoryAggroStore(AggroStore):
    """
    メモリ上で (spot_id, victim_id) -> { attacker_id -> (amount, last_seen_tick) } を保持する実装。
    スレッドセーフにするためロックを使用する。
    """

    def __init__(self) -> None:
        # (spot_id, victim_id) -> Dict[attacker_id, Tuple[amount, last_seen_tick]]
        self._store: Dict[
            Tuple[SpotId, WorldObjectId], Dict[WorldObjectId, Tuple[int, int]]
        ] = {}
        self._lock = Lock()

    def add_aggro(
        self,
        spot_id: SpotId,
        victim_id: WorldObjectId,
        attacker_id: WorldObjectId,
        amount: int = 1,
        current_tick: int = 0,
    ) -> None:
        if amount <= 0:
            raise ValueError(f"amount must be positive, got {amount}")
        key = (spot_id, victim_id)
        with self._lock:
            if key not in self._store:
                self._store[key] = {}
            entry = self._store[key].get(attacker_id, (0, 0))
            new_amount = entry[0] + amount
            self._store[key][attacker_id] = (new_amount, current_tick)

    def get_threat_by_attacker(
        self,
        spot_id: SpotId,
        attacker_id: WorldObjectId,
        current_tick: int = 0,
        memory_policy: Optional[AggroMemoryPolicy] = None,
    ) -> Dict[WorldObjectId, int]:
        result: Dict[WorldObjectId, int] = {}
        with self._lock:
            for (sid, victim_id), by_attacker in self._store.items():
                if sid != spot_id:
                    continue
                if attacker_id not in by_attacker:
                    continue
                amount, last_seen_tick = by_attacker[attacker_id]
                if amount <= 0:
                    continue
                if memory_policy is not None and memory_policy.is_forgotten(
                    current_tick, last_seen_tick
                ):
                    continue
                result[victim_id] = amount
        return result
