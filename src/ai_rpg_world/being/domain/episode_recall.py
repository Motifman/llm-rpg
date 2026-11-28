from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import Episode, EpisodeRepository
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeRecallLimitExceededException,
    EpisodeValidationException,
)


@dataclass(frozen=True)
class EpisodeRecallHandles:
    """1 回に思い出す呼び名。同じ呼び名は 1 件と数え、書かれた順に 1 度だけ持つ。"""

    handles: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.handles:
            raise EpisodeValidationException("handles must not be empty")
        if len(set(self.handles)) != len(self.handles):
            raise EpisodeValidationException("handles must not repeat")

    @classmethod
    def within(cls, handles: Sequence[str], *, limit: int) -> EpisodeRecallHandles:
        """上限を超えたら、一部だけ思い出さずに断る。どれを落としたかを本人が知らないまま 1 手が終わるため (D1623-2)。"""
        if limit < 1:
            raise EpisodeValidationException("limit must be >= 1")
        unique = tuple(dict.fromkeys(handles))
        if len(unique) > limit:
            raise EpisodeRecallLimitExceededException(limit)
        return cls(unique)


@dataclass(frozen=True)
class RecallResult:
    """``episode`` が None なら、その呼び名の記憶は無い。"""

    handle: str
    episode: Episode | None


def recall_episodes(
    repository: EpisodeRepository,
    being_id: BeingId,
    handles: EpisodeRecallHandles,
    *,
    turn: int,
) -> tuple[RecallResult, ...]:
    """どれか 1 件でもターンが決まりに合わなければ、どれも書き戻さない。"""
    results = []
    for handle in handles.handles:
        found = repository.find_by_handle(being_id, handle)
        if found is not None:
            found.recall(turn=turn)
        results.append(RecallResult(handle=handle, episode=found))
    for result in results:
        if result.episode is not None:
            repository.save(result.episode)
    return tuple(results)


__all__ = ["EpisodeRecallHandles", "RecallResult", "recall_episodes"]
