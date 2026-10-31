"""呼び名をまとめて受け取り、エピソードを呼び出す。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import Episode, EpisodeRepository
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeValidationException,
)


@dataclass(frozen=True)
class RecallResult:
    """``episode`` が None なら、その呼び名の記憶は無い。"""

    handle: str
    episode: Episode | None


def recall_episodes(
    repository: EpisodeRepository,
    being_id: BeingId,
    handles: Sequence[str],
    *,
    turn: int,
) -> tuple[RecallResult, ...]:
    """保存先から取った写しを呼び出し、書き戻して、その写しを返す。同じ呼び名は 1 回の呼び出しで 1 度だけ数え、結果も 1 件にする。

    そのため結果の件数は ``handles`` の件数より少ないことがある。

    どれか 1 件でもターンが決まりに合わなければ、どれも書き戻さない。
    """
    if not handles:
        raise EpisodeValidationException("handles must not be empty")
    unique = list(dict.fromkeys(handles))
    results = []
    for handle in unique:
        found = repository.find_by_handle(being_id, handle)
        if found is not None:
            found.recall(turn=turn)
        results.append(RecallResult(handle=handle, episode=found))
    for result in results:
        if result.episode is not None:
            repository.save(result.episode)
    return tuple(results)


__all__ = ["RecallResult", "recall_episodes"]
