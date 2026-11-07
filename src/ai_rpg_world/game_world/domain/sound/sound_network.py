from __future__ import annotations

import heapq
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.sound.sound_level import SoundLevel, SoundLoss
from ai_rpg_world.game_world.domain.value_object import SpotId


@final
@dataclass(frozen=True)
class NotReached: ...


@final
@dataclass(frozen=True)
class SoundLink:
    ends: tuple[SpotId, SpotId]
    loss: SoundLoss


@final
@dataclass(frozen=True)
class SoundReach:
    levels: Mapping[SpotId, SoundLevel]

    def __post_init__(self) -> None:
        object.__setattr__(self, "levels", MappingProxyType(dict(self.levels)))

    def level_at(self, spot: SpotId) -> SoundLevel | NotReached:
        return self.levels.get(spot, NotReached())


@final
@dataclass(frozen=True)
class SoundNetwork:
    links: tuple[SoundLink, ...]

    def spread(self, origin: SpotId, start: SoundLevel, stop_below: SoundLevel) -> SoundReach:
        neighbours: dict[SpotId, list[tuple[SpotId, SoundLoss]]] = {}
        for link in self.links:
            a, b = link.ends
            neighbours.setdefault(a, []).append((b, link.loss))
            neighbours.setdefault(b, []).append((a, link.loss))

        smallest_loss: dict[SpotId, int] = {origin: 0}
        # 同じ合計の減衰で並んだとき SpotId どうしを比べないよう、積んだ順の番号を挟む。
        frontier: list[tuple[int, int, SpotId]] = [(0, 0, origin)]
        pushed = 1
        levels: dict[SpotId, SoundLevel] = {}
        while frontier:
            total, _, spot = heapq.heappop(frontier)
            if spot in levels:
                continue
            level = start.weakened_by(SoundLoss(total))
            if level.is_below(stop_below):
                continue
            levels[spot] = level
            for neighbour, loss in neighbours.get(spot, ()):
                candidate = total + loss.value
                if candidate < smallest_loss.get(neighbour, candidate + 1):
                    smallest_loss[neighbour] = candidate
                    heapq.heappush(frontier, (candidate, pushed, neighbour))
                    pushed += 1
        return SoundReach(levels=levels)
