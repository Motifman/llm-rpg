from __future__ import annotations

from ai_rpg_world.being.application.receive_action_result import ReceiveActionResult, ReceiveActionResultCommand
from ai_rpg_world.being.contract import (
    UNKNOWN,
    AgentMove,
    Observation,
    ObservedTime,
    OwnActionResult,
    PersonInText,
    TextWithPeople,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.short_term_memory import Attempt, ObservedOutcome
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)

GEN = BeingId("gen")
SAYO = PersonInText(handle=2, appearance="髪を結った娘", visible_name="サヨ")


class TestReceiveActionResultNamesPeople:
    """ReceiveActionResult が、結果の本文の人の穴を、受け取ったときの呼び名で埋めて短期記憶に残すことを保証する。"""

    def test_people_in_the_result_are_named_as_seen_when_received(self) -> None:
        """ゲンがサヨに鍵を渡そうとして「{target}は手がふさがっている」で断られると、試みの結果は「サヨは手がふさがっている」で残る。"""
        memories = InMemoryShortTermMemoryRepository()
        clock = InMemoryMemoryTurnClock()
        memory = memories.get(GEN)
        memory.act(AgentMove(call_id="call_1", tool_name="give_item", arguments={}), current_turn=1)
        memories.save(memory)
        clock.advance_turn(GEN)
        result = Observation(
            body=TextWithPeople(template="{target}は手がふさがっている", people={"target": SAYO}),
            route=OwnActionResult(call_id="call_1", succeeded=False),
            time=ObservedTime(display="1 日目 06:00"),
            subject_is_self=True,
            subject_name=UNKNOWN,
            source=UNKNOWN,
            place=UNKNOWN,
            addressed_to_self=True,
        )

        ReceiveActionResult(memories, clock).execute(ReceiveActionResultCommand(GEN, result))

        [attempt] = memories.get(GEN).unsummarized()
        assert isinstance(attempt, Attempt) and isinstance(attempt.result, ObservedOutcome)
        assert attempt.result.observation.body == "サヨは手がふさがっている"
