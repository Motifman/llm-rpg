"""DefaultAtmosphereBuffer 実装。

プレイヤーごとに最大 capacity 件の AtmosphereEntry を保持する in-memory リング。
古いものから捨てる。プロンプト builder は recent() で直近数件を取り出す想定。
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List

from ai_rpg_world.application.observation.contracts.atmosphere_dtos import (
    AtmosphereEntry,
)
from ai_rpg_world.application.observation.contracts.atmosphere_interfaces import (
    IAtmosphereBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class DefaultAtmosphereBuffer(IAtmosphereBuffer):
    """in-memory リングバッファ。プレイヤーごとに独立。"""

    def __init__(self, capacity: int = 8) -> None:
        if capacity < 1:
            raise ValueError("DefaultAtmosphereBuffer.capacity must be >= 1")
        self._capacity = capacity
        self._buf: Dict[int, Deque[AtmosphereEntry]] = {}

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def append(self, player_id: PlayerId, entry: AtmosphereEntry) -> None:
        key = self._key(player_id)
        if key not in self._buf:
            self._buf[key] = deque(maxlen=self._capacity)
        self._buf[key].append(entry)

    def recent(
        self,
        player_id: PlayerId,
        max_count: int,
    ) -> List[AtmosphereEntry]:
        if max_count < 0:
            raise ValueError("max_count must be >= 0")
        if max_count == 0:
            return []
        entries = self._buf.get(self._key(player_id))
        if not entries:
            return []
        # 新しい順で返す
        return list(reversed(list(entries)))[:max_count]

    def all(self, player_id: PlayerId) -> List[AtmosphereEntry]:
        return list(self._buf.get(self._key(player_id), []))

    def clear(self, player_id: PlayerId) -> None:
        key = self._key(player_id)
        if key in self._buf:
            self._buf[key].clear()
