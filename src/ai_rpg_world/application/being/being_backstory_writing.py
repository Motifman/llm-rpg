"""短期記憶が頼んだいきさつを裏で作り、その Being のターンの始めに短期記憶へ入れる (#1824、design_decisions D1824-12)。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter
from ai_rpg_world.being.domain.short_term_memory import (
    Backstory,
    BackstoryAsked,
    ShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


@dataclass(frozen=True)
class WrittenBackstory:
    """裏のスレッドで作ったいきさつ。その Being のターンの始めに入れる。"""

    being_id: BeingId
    backstory: Backstory


class BeingBackstoryWriting:
    """``note_person`` と ``apply`` をターンを進めるスレッドで、``write`` を裏のスレッドで呼ぶ (design_decisions D1837 の 4)。"""

    def __init__(
        self,
        *,
        writer: BackstoryWriter,
        store: ShortTermMemoryRepository,
        persona_of: Callable[[BeingId], tuple[str, str]],
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._writer = writer
        self._store = store
        self._persona_of = persona_of
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        self._people: dict[BeingId, tuple[str, str]] = {}

    def note_person(self, request: BackstoryAsked) -> None:
        """本人の名前と性格は Being の保存先を走査して引くので、裏のスレッドではなく、配送に渡す前にここで引いておく。"""
        if request.being_id not in self._people:
            self._people[request.being_id] = self._persona_of(request.being_id)

    def write(self, request: BackstoryAsked) -> WrittenBackstory:
        """短期記憶には触らない。書けなければ例外を投げ、非同期の配送が失敗として trace に残す。"""
        self_name, persona = self._people[request.being_id]
        backstory = self._writer.write(
            self_name=self_name,
            persona=persona,
            experiences=request.experiences,
            previous=request.latest_backstory,
            until_turn=request.until_turn,
            written_turn=request.turn,
        )
        return WrittenBackstory(being_id=request.being_id, backstory=backstory)

    def apply(self, written: WrittenBackstory) -> None:
        memory = self._store.get(written.being_id)
        memory.add_backstory(written.backstory)
        self._store.save(memory)
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        recorder.record(
            TraceEventKind.BEING_BACKSTORY_WRITTEN,
            tick=self._current_tick_provider(),
            being_id=written.being_id.value,
            until_turn=written.backstory.until_turn,
            written_turn=written.backstory.written_turn,
            flow=written.backstory.flow,
            mood=written.backstory.mood,
        )


__all__ = ["BeingBackstoryWriting", "WrittenBackstory"]
