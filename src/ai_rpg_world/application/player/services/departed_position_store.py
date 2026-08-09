"""物理グラフに載らない、去った主体の現在地を保持する。"""

from __future__ import annotations

from typing import Mapping

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class DepartedPositionStore:
    """去った主体の spot を、物理的な在席とは別の世界状態として保持する。"""

    def __init__(self) -> None:
        self._positions: dict[PlayerId, SpotId] = {}

    def place(self, player_id: PlayerId, spot_id: SpotId) -> None:
        self._positions[player_id] = spot_id

    def find(self, player_id: PlayerId) -> SpotId | None:
        return self._positions.get(player_id)

    def move(self, player_id: PlayerId, spot_id: SpotId) -> None:
        if player_id not in self._positions:
            raise ValueError(
                f"departed player is not placed: player_id={int(player_id)}"
            )
        self._positions[player_id] = spot_id

    def remove(self, player_id: PlayerId) -> None:
        self._positions.pop(player_id, None)

    def players_at(self, spot_id: SpotId) -> tuple[PlayerId, ...]:
        return tuple(
            player_id
            for player_id, current in sorted(
                self._positions.items(), key=lambda item: int(item[0])
            )
            if current == spot_id
        )

    def snapshot(self) -> dict[PlayerId, SpotId]:
        return dict(self._positions)

    def replace_all(self, positions: Mapping[PlayerId, SpotId]) -> None:
        normalized: dict[PlayerId, SpotId] = {}
        for player_id, spot_id in positions.items():
            if not isinstance(player_id, PlayerId):
                raise TypeError(f"player_id must be PlayerId: {player_id!r}")
            if not isinstance(spot_id, SpotId):
                raise TypeError(f"spot_id must be SpotId: {spot_id!r}")
            normalized[player_id] = spot_id
        self._positions = normalized


__all__ = ["DepartedPositionStore"]
