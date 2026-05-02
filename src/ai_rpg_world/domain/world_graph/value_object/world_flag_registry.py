from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class WorldFlagRegistry:
    """ワールドフラグの不変集合（スポットグラフ脱出ゲーム等で使用）"""

    _flags: FrozenSet[str]

    @classmethod
    def empty(cls) -> WorldFlagRegistry:
        return cls(frozenset())

    @classmethod
    def from_frozen_set(cls, flags: FrozenSet[str]) -> WorldFlagRegistry:
        """既存のフラグ集合から構築（インタラクション結果の一括反映用）。"""
        return cls(flags)

    @classmethod
    def of(cls, *names: str) -> WorldFlagRegistry:
        return cls(frozenset(names))

    def contains(self, name: str) -> bool:
        return name in self._flags

    def with_added(self, *names: str) -> WorldFlagRegistry:
        return WorldFlagRegistry(self._flags.union(names))

    def with_removed(self, *names: str) -> WorldFlagRegistry:
        return WorldFlagRegistry(self._flags.difference(names))

    def as_frozen_set(self) -> FrozenSet[str]:
        return self._flags

    def merge(self, other: WorldFlagRegistry) -> WorldFlagRegistry:
        return WorldFlagRegistry(self._flags.union(other._flags))
