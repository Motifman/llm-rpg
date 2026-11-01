"""Being の持ち物を保存先から集め、環境の材料と合わせて、このターンの作業記憶を組む (#1630)。"""

from __future__ import annotations

from typing import Protocol

from ai_rpg_world.being.application.backstory_text import backstory_text
from ai_rpg_world.being.application.conduct_text import conduct_text
from ai_rpg_world.being.application.episode_index_text import format_episode_index
from ai_rpg_world.being.application.known_people import render_known_people
from ai_rpg_world.being.application.memo_book_text import format_memo_book
from ai_rpg_world.being.application.recent_events_text import recent_events_text
from ai_rpg_world.being.contract import OfferedBeingTools, Orientation, Scene
from ai_rpg_world.being.domain.acquaintance import AcquaintanceRepository
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import Episode, EpisodeRepository
from ai_rpg_world.being.domain.episode_index_selection import RecalledRisesToTop
from ai_rpg_world.being.domain.memo_book import MemoBookRepository
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryRepository
from ai_rpg_world.being.domain.working_memory import Closing, MemoryTexts, WorkingMemory


class BeingLookup(Protocol):
    """Being の保存先のうち、ここで使う問い合わせ。保存先の型は、まだゲームの側 (#1469) にある。"""

    def find_by_id(self, being_id: BeingId) -> Being | None: ...


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
        episode_index_limit: int,
    ) -> None:
        self._beings = beings
        self._short_term_memories = short_term_memories
        self._acquaintances = acquaintances
        self._episodes = episodes
        self._memo_books = memo_books
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
        environment_name = self._environment_name(being_id)
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
            orientation=orientation,
            conduct=conduct_text(being_tools),
            imposed_goal=imposed_goal,
            memory=memory,
            scene=scene,
            closing=closing,
        )

    def episodes_in_index(self, being_id: BeingId) -> tuple[Episode, ...]:
        """【思い出せる出来事】に並べるエピソード。目次の文と、目次に出したものの記録が同じ選び方を使う。"""
        return RecalledRisesToTop().select(self._episodes.list_by_being(being_id), limit=self._episode_index_limit)

    def _environment_name(self, being_id: BeingId) -> str:
        being = self._beings.find_by_id(being_id)
        if being is None or being.attachment is None:
            raise LookupError(f"Being {being_id.value} is not in any environment")
        return being.attachment.environment_name


__all__ = ["CurrentWorkingMemory"]
