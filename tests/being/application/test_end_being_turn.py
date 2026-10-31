from __future__ import annotations

from ai_rpg_world.being.application.end_being_turn import EndBeingTurn, EndBeingTurnCommand
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.short_term_memory import AwaitedBackstory, ShortTermMemoryRangeFilledEvent
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)

ADA = BeingId("being_p1")


def _seen() -> Observation:
    return Observation(
        body="鐘が鳴った",
        route=SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )


class TestEndBeingTurn:
    """EndBeingTurn が、その Being の短期記憶のターンを終わらせて保存することを保証する (design_decisions D1824-21)。"""

    def test_turn_end_is_saved_and_its_events_are_handed_off(self) -> None:
        """範囲が埋まるターンを終わらせると、短期記憶はいきさつを待ち始めて保存され、範囲が埋まったイベントが配送器に渡る。"""
        handed: list[object] = []
        store = InMemoryShortTermMemoryRepository(handoff=handed.extend)
        memory = store.get(ADA)
        for turn in range(0, 20):
            memory.perceive(_seen(), current_turn=turn)
        store.save(memory)

        EndBeingTurn(store).execute(EndBeingTurnCommand(being_id=ADA, turn=20))

        assert store.get(ADA).awaited_backstory == AwaitedBackstory(until_turn=10, since_turn=20)
        assert [type(e) for e in handed] == [ShortTermMemoryRangeFilledEvent]

    def test_turn_end_with_nothing_to_report_changes_nothing(self) -> None:
        """範囲が埋まっていないターンを終わらせても、短期記憶は変わらず、配送器には何も渡らない。"""
        handed: list[object] = []
        store = InMemoryShortTermMemoryRepository(handoff=handed.extend)

        EndBeingTurn(store).execute(EndBeingTurnCommand(being_id=ADA, turn=3))

        assert (store.get(ADA).is_empty(), handed) == (True, [])
