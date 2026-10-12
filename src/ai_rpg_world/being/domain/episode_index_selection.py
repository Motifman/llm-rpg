"""目次に載せるエピソードの選び方。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ai_rpg_world.being.domain.episode import Episode
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeValidationException,
)


class EpisodeIndexSelection(ABC):
    """どれを使うかと N は、profile の設定から組み立ての段で選ぶ。"""

    def select(self, episodes: Sequence[Episode], *, limit: int) -> tuple[Episode, ...]:
        """``episodes`` は保存の側が足した順に並べたもの。表示する順に ``limit`` 件まで返す。"""
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise EpisodeValidationException("limit must be int >= 0")
        return self._ordered(episodes)[:limit]

    @abstractmethod
    def _ordered(self, episodes: Sequence[Episode]) -> tuple[Episode, ...]: ...


class NewestFirst(EpisodeIndexSelection):
    """書いた時の新しい順。同じターンなら後から足した方を先に出す。"""

    def _ordered(self, episodes: Sequence[Episode]) -> tuple[Episode, ...]:
        return tuple(sorted(reversed(episodes), key=lambda e: e.written_turn, reverse=True))


__all__ = ["EpisodeIndexSelection", "NewestFirst"]
