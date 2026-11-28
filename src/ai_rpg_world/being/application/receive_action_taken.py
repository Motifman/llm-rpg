from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.application.names_for_people import text_naming_people
from ai_rpg_world.being.contract import ActionTaken, Observation, OwnAction
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader
from ai_rpg_world.being.domain.short_term_memory import AttemptTaken, ShortTermMemoryRepository


@dataclass(frozen=True)
class ReceiveActionTakenCommand:
    """``noticed`` は、その行為について本人が知ったことの観測。経路は ``OwnAction``。知ったことが無ければ None。"""

    being_id: BeingId
    taken: ActionTaken
    noticed: Observation | None = None

    def __post_init__(self) -> None:
        if self.noticed is not None and not isinstance(self.noticed.route, OwnAction):
            raise ValueError("what was noticed about one's own action must come through the OwnAction route")


class ReceiveActionTaken:
    def __init__(self, short_term_memories: ShortTermMemoryRepository, turn_reader: MemoryTurnReader) -> None:
        self._short_term_memories = short_term_memories
        self._turn_reader = turn_reader

    def execute(self, command: ReceiveActionTakenCommand) -> None:
        memory = self._short_term_memories.get(command.being_id)
        turn = self._turn_reader.current_turn(command.being_id)
        # 呼び名は受け取ったときのもので埋める。観測と同じく、あとで名前を知っても記憶は書き換えない
        memory.receive_response(AttemptTaken(command.taken.with_people_named(text_naming_people)), current_turn=turn)
        if command.noticed is not None:
            memory.perceive(command.noticed.with_people_named(text_naming_people), current_turn=turn)
        self._short_term_memories.save(memory)


__all__ = ["ReceiveActionTaken", "ReceiveActionTakenCommand"]
