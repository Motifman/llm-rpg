"""短期記憶の範囲が埋まったら、いきさつとエピソードを裏のスレッドで書き、Being が頼んだときに記憶に入れる (#2271)。"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from threading import Lock

from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory
from ai_rpg_world.being.application.handlers.write_backstory_handler import WriteBackstoryHandler
from ai_rpg_world.being.application.handlers.write_episodes_handler import WriteEpisodesHandler
from ai_rpg_world.being.application.memory_writing_in_background import MemoryWritingInBackground
from ai_rpg_world.being.application.writing_circumstances import CircumstancesOfBeings
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.being.domain.episode_writer import EpisodeWriter
from ai_rpg_world.being.domain.short_term_memory import (
    ShortTermMemoryBackstoryOverdueEvent,
    ShortTermMemoryRangeFilledEvent,
    ShortTermMemoryRepository,
)
from ai_rpg_world.eventing import AsyncEventExecutor, AsyncFailure, DomainEvent, EventDispatcher
from ai_rpg_world.eventing.delivery import DeliveryChannel, DeliveryGuarantee


class MemoryWritingOnThreads(MemoryWritingInBackground):
    def __init__(self, *, wait_limit_seconds: float, workers: int = 2, max_pending: int = 100) -> None:
        if not math.isfinite(wait_limit_seconds) or wait_limit_seconds < 0:
            raise ValueError("wait_limit_seconds must be a finite number >= 0")
        self._wait_limit_seconds = wait_limit_seconds
        self._failures: Counter[str] = Counter()
        self._failures_lock = Lock()
        self._executor = AsyncEventExecutor(
            failure_observer=self._count_failure, max_workers=workers, max_pending=max_pending
        )
        self._dispatcher: EventDispatcher[None] = EventDispatcher(
            failure_observer=lambda channel, guarantee, event, handler, error: self._count("submit_failed")
        )

    def handoff(self, events: Sequence[DomainEvent]) -> None:
        self._dispatcher.handoff(events)

    def write_with(
        self,
        *,
        backstory_writer: BackstoryWriter,
        episode_writer: EpisodeWriter,
        short_term_memories: ShortTermMemoryRepository,
        episodes: EpisodeRepository,
        circumstances: CircumstancesOfBeings,
    ) -> None:
        backstory = WriteBackstoryHandler(
            writer=backstory_writer,
            store=short_term_memories,
            persona_of=circumstances.persona_of,
            persona_text_of=circumstances.persona_text_of,
        )
        for event_type in (ShortTermMemoryRangeFilledEvent, ShortTermMemoryBackstoryOverdueEvent):
            self._dispatcher.register_async_after_commit(
                event_type,
                backstory,
                channel=DeliveryChannel.AUXILIARY,
                guarantee=DeliveryGuarantee.BEST_EFFORT,
                executor=self._executor,
                recipient_key=lambda event: event.being_id.value,
            )
        self._dispatcher.register_async_after_commit(
            ShortTermMemoryRangeFilledEvent,
            WriteEpisodesHandler(
                writer=episode_writer,
                add_episodes=AddEpisodesToMemory(episodes),
                persona_of=circumstances.persona_of,
                circumstances_of=circumstances.circumstances_of,
            ),
            channel=DeliveryChannel.AUXILIARY,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
            executor=self._executor,
            recipient_key=lambda event: event.being_id.value,
        )

    def take_in_finished(self, being_id: BeingId) -> None:
        self._executor.apply_results(being_id.value)

    def finish(self, being_id: BeingId) -> bool:
        finished = self._executor.wait_for(being_id.value, timeout=self._wait_limit_seconds)
        if not finished:
            self._count("wait_limit_passed")
        self._executor.apply_results(being_id.value)
        return finished

    def failures(self) -> dict[str, int]:
        """書けなかったか、待ちきれなかった数を理由ごとに返す。"""
        with self._failures_lock:
            return dict(self._failures)

    def shutdown(self) -> None:
        """待ちきれなかった書き起こしも、上限の時間までに書き終われば記憶に入れる。書いたものを捨てない。"""
        self._executor.shutdown(timeout=self._wait_limit_seconds)
        self._executor.apply_all_results()

    def _count_failure(self, failure: AsyncFailure) -> None:
        self._count(failure.reason)

    def _count(self, reason: str) -> None:
        with self._failures_lock:
            self._failures[reason] += 1


__all__ = ["MemoryWritingOnThreads"]
