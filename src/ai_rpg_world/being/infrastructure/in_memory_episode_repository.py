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


class InMemoryEpisodeRepository(EpisodeRepository):
    def __init__(self) -> None:
        self._by_being: dict[BeingId, dict[str, Episode]] = {}

    def add(self, being_id: BeingId, episode: Episode) -> None:
        book = self._by_being.get(being_id, {})
        _require_no_overlap([*book.values(), episode])
        self._by_being[being_id] = {**book, episode.episode_id: episode}

    def find_by_handle(self, being_id: BeingId, handle: str) -> Episode | None:
        for episode in self._by_being.get(being_id, {}).values():
            if episode.handle == handle:
                return episode
        return None

    def list_by_being(self, being_id: BeingId) -> tuple[Episode, ...]:
        return tuple(self._by_being.get(being_id, {}).values())

    def save(self, being_id: BeingId, episode: Episode) -> None:
        book = self._by_being.get(being_id, {})
        known = book.get(episode.episode_id)
        if known is None:
            raise EpisodeNotFoundException(f"no episode {episode.episode_id!r} for {being_id}")
        if not episode.follows(known):
            raise EpisodeConflictException(
                f"{episode.episode_id!r} is not a later version of the saved episode"
            )
        book[episode.episode_id] = episode

    def replace_all_by_being(self, being_id: BeingId, episodes: Sequence[Episode]) -> None:
        _require_no_overlap(episodes)
        if not episodes:
            self._by_being.pop(being_id, None)
            return
        self._by_being[being_id] = {e.episode_id: e for e in episodes}


__all__ = ["InMemoryEpisodeRepository"]
