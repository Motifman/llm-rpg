from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.being.domain.episode import Episode, EpisodeRepository
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeConflictException,
    EpisodeNotFoundException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


def _require_no_overlap(episodes: Sequence[Episode]) -> None:
    ids = [e.episode_id for e in episodes]
    handles = [e.handle for e in episodes]
    if len(set(ids)) != len(ids):
        raise EpisodeConflictException("the same episode_id appears twice")
    if len(set(handles)) != len(handles):
        raise EpisodeConflictException("the same handle appears twice")


def _copy(episode: Episode) -> Episode:
    """目次や履歴は中身の変わらない値なので、同じ中身を持つ新しい集約を作れば写しになる。ためたイベントは写さない。"""
    return Episode(
        episode_id=episode.episode_id,
        handle=episode.handle,
        environment_name=episode.environment_name,
        written_turn=episode.written_turn,
        index=episode.index,
        body=episode.body,
        recall_count=episode.recall_count,
        last_recalled_turn=episode.last_recalled_turn,
        index_history=episode.index_history,
    )


class InMemoryEpisodeRepository(EpisodeRepository):
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。"""

    def __init__(self) -> None:
        self._by_being: dict[BeingId, dict[str, Episode]] = {}

    def add(self, being_id: BeingId, episode: Episode) -> None:
        book = self._by_being.get(being_id, {})
        _require_no_overlap([*book.values(), episode])
        self._by_being[being_id] = {**book, episode.episode_id: _copy(episode)}

    def find_by_handle(self, being_id: BeingId, handle: str) -> Episode | None:
        for episode in self._by_being.get(being_id, {}).values():
            if episode.handle == handle:
                return _copy(episode)
        return None

    def list_by_being(self, being_id: BeingId) -> tuple[Episode, ...]:
        return tuple(_copy(e) for e in self._by_being.get(being_id, {}).values())

    def save(self, being_id: BeingId, episode: Episode) -> None:
        book = self._by_being.get(being_id, {})
        known = book.get(episode.episode_id)
        if known is None:
            raise EpisodeNotFoundException(f"no episode {episode.episode_id!r} for {being_id}")
        if not episode.follows(known):
            raise EpisodeConflictException(
                f"{episode.episode_id!r} is not a later version of the saved episode"
            )
        book[episode.episode_id] = _copy(episode)

    def replace_all_by_being(self, being_id: BeingId, episodes: Sequence[Episode]) -> None:
        _require_no_overlap(episodes)
        if not episodes:
            self._by_being.pop(being_id, None)
            return
        self._by_being[being_id] = {e.episode_id: _copy(e) for e in episodes}


__all__ = ["InMemoryEpisodeRepository"]
