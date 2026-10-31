"""短期記憶の範囲が埋まったか、いきさつが遅れているとき、いきさつを書いて短期記憶に入れる (#1824、design_decisions D1824-18)。"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.being.application.add_backstory_to_short_term_memory import (
    AddBackstoryToShortTermMemory,
    AddBackstoryToShortTermMemoryCommand,
)
from ai_rpg_world.being.application.write_backstory import WriteBackstory, WriteBackstoryCommand
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import (
    ShortTermMemoryBackstoryOverdueEvent,
    ShortTermMemoryRangeFilledEvent,
    ShortTermMemoryRepository,
)
from ai_rpg_world.eventing import AsyncEventHandler

RangeToSummarize = ShortTermMemoryRangeFilledEvent | ShortTermMemoryBackstoryOverdueEvent


class WriteBackstoryHandler(
    AsyncEventHandler[RangeToSummarize, WriteBackstoryCommand, AddBackstoryToShortTermMemoryCommand]
):
    """``persona_of`` は Being の保存先から人柄を引き、``persona_text_of`` は人格の文を返す。

    人格の文は、``persona_prompt`` を分けるまで (#1339 / #1548)、ゲームの側がプレイヤーを走査して引く関数を渡す
    (design_decisions D1469-2)。どちらも保存先を引くので、ターンを進めるスレッドで動く ``prepare`` で呼ぶ。
    """

    def __init__(
        self,
        *,
        writer: BackstoryWriter,
        store: ShortTermMemoryRepository,
        persona_of: Callable[[BeingId], Persona],
        persona_text_of: Callable[[BeingId], str],
    ) -> None:
        self._write = WriteBackstory(writer)
        self._add = AddBackstoryToShortTermMemory(store)
        self._persona_of = persona_of
        self._persona_text_of = persona_text_of

    def prepare(self, event: RangeToSummarize) -> WriteBackstoryCommand:
        return WriteBackstoryCommand(
            being_id=event.being_id,
            persona=self._persona_of(event.being_id),
            persona_text=self._persona_text_of(event.being_id),
            experiences=event.experiences,
            previous=event.latest_backstory,
            until_turn=event.until_turn,
            written_turn=event.turn,
        )

    def handle(self, command: WriteBackstoryCommand) -> AddBackstoryToShortTermMemoryCommand:
        written = self._write.execute(command)
        return AddBackstoryToShortTermMemoryCommand(
            being_id=command.being_id, backstory=written.backstory, truncated=written.truncated
        )

    def apply(self, result: AddBackstoryToShortTermMemoryCommand) -> None:
        self._add.execute(result)


__all__ = ["RangeToSummarize", "WriteBackstoryHandler"]
