from __future__ import annotations

from typing import Protocol

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class ISpotExplorationProgressStore(Protocol):
    """プレイヤー×スポットの累積探索回数（スポットグラフ用）。"""

    def increment_and_get(self, player_id: PlayerId, spot_id: SpotId) -> int:
        """探索を1回実行したものとしてカウントし、累積回数を返す。"""
        ...


class InMemorySpotExplorationProgressStore:
    """テスト・デモ用のインメモリ探索回数ストア。"""

    def __init__(self) -> None:
        self._counts: dict[tuple[int, int], int] = {}

    def increment_and_get(self, player_id: PlayerId, spot_id: SpotId) -> int:
        key = (int(player_id), int(spot_id))
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]
