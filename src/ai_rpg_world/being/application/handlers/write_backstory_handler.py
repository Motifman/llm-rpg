"""短期記憶の範囲が埋まったか、いきさつが遅れているとき、いきさつを書いて短期記憶に入れる (#1824、design_decisions D1824-18)。"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.being.application.add_backstory_to_short_term_memory import (
    AddBackstoryToShortTermMemory,
    AddBackstoryToShortTermMemoryCommand,
)
from ai_rpg_world.being.application.write_backstory import WriteBackstory, WriteBackstoryCommand
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter
from ai_rpg_world.being.domain.short_term_memory import (
    ShortTermMemoryBackstoryOverdueEvent,
    ShortTermMemoryRangeFilledEvent,
    ShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.eventing import AsyncEventHandler

RangeToSummarize = ShortTermMemoryRangeFilledEvent | ShortTermMemoryBackstoryOverdueEvent


class WriteBackstoryHandler(
    AsyncEventHandler[RangeToSummarize, WriteBackstoryCommand, AddBackstoryToShortTermMemoryCommand]
):
    """``persona_of`` は、本人の名前と人格の文を返す。

    Being の ``Persona`` に移すまでは、ゲームの側がプレイヤーを走査して引く関数を渡す (#1469)。保存先を走査するので、
    ターンを進めるスレッドで動く ``prepare`` で呼ぶ。
    """

    def __init__(
        self,
        *,
        writer: BackstoryWriter,
        store: ShortTermMemoryRepository,
        persona_of: Callable[[BeingId], tuple[str, str]],
    ) -> None:
        self._write = WriteBackstory(writer)
        self._add = AddBackstoryToShortTermMemory(store)
        self._persona_of = persona_of

    def prepare(self, event: RangeToSummarize) -> WriteBackstoryCommand:
        self_name, persona = self._persona_of(event.being_id)
        return WriteBackstoryCommand(
            being_id=event.being_id,
            self_name=self_name,
            persona=persona,
            experiences=event.experiences,
            previous=event.latest_backstory,
            until_turn=event.until_turn,
            written_turn=event.turn,
        )

    def handle(self, command: WriteBackstoryCommand) -> AddBackstoryToShortTermMemoryCommand:
        return AddBackstoryToShortTermMemoryCommand(being_id=command.being_id, backstory=self._write.execute(command))

    def apply(self, result: AddBackstoryToShortTermMemoryCommand) -> None:
        self._add.execute(result)


__all__ = ["RangeToSummarize", "WriteBackstoryHandler"]
