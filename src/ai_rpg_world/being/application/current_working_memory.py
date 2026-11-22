"""Being の持ち物を保存先から集め、環境の材料と合わせて、このターンの作業記憶を組む (#1630)。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ai_rpg_world.being.application.backstory_text import backstory_text
from ai_rpg_world.being.application.conduct_text import conduct_text
from ai_rpg_world.being.application.episode_index_text import format_episode_index
from ai_rpg_world.being.application.known_people import render_known_people
from ai_rpg_world.being.application.memo_book_text import format_memo_book
from ai_rpg_world.being.application.names_for_people import text_naming_people
from ai_rpg_world.being.application.recent_events_text import recent_events_text
from ai_rpg_world.being.contract import Description, Here, OfferedBeingTools, Orientation, Scene, TextWithPeople
from ai_rpg_world.being.domain.acquaintance import AcquaintanceRepository
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import Episode, EpisodeRepository
from ai_rpg_world.being.domain.episode_index_selection import RecalledRisesToTop
from ai_rpg_world.being.domain.memo_book import MemoBookRepository
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryRepository
from ai_rpg_world.being.domain.visited_places import VisitedPlacesRepository
from ai_rpg_world.being.domain.working_memory import Closing, MemoryTexts, WorkingMemory

CURRENT_PLACE_LABEL = "現在地"
FIRST_VISIT_MARK = "(初めて訪れた)"


class BeingLookup(Protocol):
    def get(self, being_id: BeingId) -> Being:
        """いなければ ``BeingNotFoundException`` で断る。"""
        ...


class CurrentWorkingMemory:
    """問い合わせ。状態を変えない。

    案内 (``Orientation``) は、環境が毎ターン場面と一緒に渡し直す。Being は案内を持たない。
    環境の名前は、Being が今いる環境 (``BeingAttachment``) の表示の名前を使う。
    """

    def __init__(
        self,
        *,
        beings: BeingLookup,
        short_term_memories: ShortTermMemoryRepository,
        acquaintances: AcquaintanceRepository,
        episodes: EpisodeRepository,
        memo_books: MemoBookRepository,
        visited_places: VisitedPlacesRepository,
        episode_index_limit: int,
    ) -> None:
        self._beings = beings
        self._short_term_memories = short_term_memories
        self._acquaintances = acquaintances
        self._episodes = episodes
        self._memo_books = memo_books
        self._visited_places = visited_places
        self._episode_index_limit = episode_index_limit

    def of(
        self,
        being_id: BeingId,
        *,
        orientation: Orientation,
        being_tools: OfferedBeingTools,
        imposed_goal: str | None,
        scene: Scene,
        closing: Closing,
    ) -> WorkingMemory:
        environment_name = self.environment_name(being_id)
        short_term = self._short_term_memories.get(being_id)
        shown_episodes = self.episodes_in_index(being_id)
        memory = MemoryTexts(
            known_people=render_known_people(
                self._acquaintances.list_by_being(being_id), environment_name=environment_name
            ),
            backstory=backstory_text(short_term),
            recent_events=recent_events_text(short_term),
            episode_index=format_episode_index(shown_episodes, current_environment_name=environment_name),
            memo=format_memo_book(self._memo_books.get(being_id), current_environment_name=environment_name),
        )
        return WorkingMemory.compose(
            orientation=Orientation(_named(orientation.descriptions)),
            conduct=conduct_text(being_tools),
            imposed_goal=imposed_goal,
            memory=memory,
            scene=Scene(
                (
                    *self._surroundings(being_id, scene.here, environment_name=environment_name),
                    *_named(scene.descriptions),
                ),
                notices=_named(scene.notices),
            ),
            closing=closing,
        )

    def episodes_in_index(self, being_id: BeingId) -> tuple[Episode, ...]:
        """【思い出せる出来事】に並べるエピソード。目次の文と、目次に出したものの記録が同じ選び方を使う。"""
        return RecalledRisesToTop().select(self._episodes.list_by_being(being_id), limit=self._episode_index_limit)

    def _surroundings(self, being_id: BeingId, here: Here | None, *, environment_name: str) -> tuple[Description, ...]:
        if here is None:
            return ()
        first = not self._visited_places.get(being_id).has_visited(environment_name=environment_name, place=here.place)
        place = f"{here.place} {FIRST_VISIT_MARK}" if first else here.place
        text = text_naming_people(here.text) if isinstance(here.text, TextWithPeople) else here.text
        return (Description(heading=here.heading, text=f"{CURRENT_PLACE_LABEL}: {place}\n{text}"),)

    def environment_name(self, being_id: BeingId) -> str:
        """Being が今いる環境の表示の名前。"""
        being = self._beings.get(being_id)
        if being.attachment is None:
            raise LookupError(f"Being {being_id.value} is not in any environment")
        return being.attachment.environment_name


def _named(descriptions: Sequence[Description]) -> tuple[Description, ...]:
    return tuple(
        Description(heading=d.heading, text=text_naming_people(d.text)) if isinstance(d.text, TextWithPeople) else d
        for d in descriptions
    )


__all__ = ["CurrentWorkingMemory"]
