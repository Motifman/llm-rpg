from __future__ import annotations

from collections.abc import Sequence

from ai_rpg_world.being.domain.episode import Episode, EpisodeRepository
from ai_rpg_world.being.infrastructure.event_handoff import EventHandoff, save_and_hand_off
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
        being_id=episode.being_id,
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
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。

    保存した集約がためたイベントは、``handoff`` に渡す。
    """

    def __init__(self, *, handoff: EventHandoff | None = None) -> None:
        self._by_being: dict[BeingId, dict[str, Episode]] = {}
        self._handoff = handoff

    def add(self, episode: Episode) -> None:
        being_id = episode.being_id
        book = self._by_being.get(being_id, {})
        _require_no_overlap([*book.values(), episode])

        def store() -> None:
            self._by_being[being_id] = {**book, episode.episode_id: _copy(episode)}

        save_and_hand_off(episode, self._handoff, store)

    def find_by_handle(self, being_id: BeingId, handle: str) -> Episode | None:
        for episode in self._by_being.get(being_id, {}).values():
            if episode.handle == handle:
                return _copy(episode)
        return None

    def list_by_being(self, being_id: BeingId) -> tuple[Episode, ...]:
        return tuple(_copy(e) for e in self._by_being.get(being_id, {}).values())

    def save(self, episode: Episode) -> None:
        being_id = episode.being_id
        book = self._by_being.get(being_id, {})
        known = book.get(episode.episode_id)
        if known is None:
            raise EpisodeNotFoundException(f"no episode {episode.episode_id!r} for {being_id}")
        if not episode.follows(known):
            raise EpisodeConflictException(f"{episode.episode_id!r} is not a later version of the saved episode")

        def store() -> None:
            book[episode.episode_id] = _copy(episode)

        save_and_hand_off(episode, self._handoff, store)

    def replace_all_by_being(self, being_id: BeingId, episodes: Sequence[Episode]) -> None:
        strangers = [e.episode_id for e in episodes if e.being_id != being_id]
        if strangers:
            raise EpisodeConflictException(f"episodes of another being cannot be put under {being_id}: {strangers}")
        _require_no_overlap(episodes)
        if not episodes:
            self._by_being.pop(being_id, None)
            return
        pending = [e for e in episodes if e.get_events()]
        if pending and self._handoff is None:
            raise RuntimeError(f"{len(pending)} episode(s) have pending events but the repository has no handoff")
        self._by_being[being_id] = {e.episode_id: _copy(e) for e in episodes}
        for episode in pending:
            save_and_hand_off(episode, self._handoff, lambda: None)


__all__ = ["InMemoryEpisodeRepository"]
