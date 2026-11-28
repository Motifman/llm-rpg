from __future__ import annotations

import pytest

from ai_rpg_world.being.application.receive_action_taken import ReceiveActionTaken, ReceiveActionTakenCommand
from ai_rpg_world.being.application.recent_events_text import recent_events_text
from ai_rpg_world.being.contract import (
    UNKNOWN,
    ActionTaken,
    AgentMove,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnAction,
    PersonInText,
    SeenOrHeard,
    TextWithPeople,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)

GEN = BeingId("gen")
SAYO = PersonInText(handle=2, appearance="髪を結った娘", visible_name="サヨ")
_TIME = ObservedTime(display="1 日目 06:00")
_ORDER = OccurrenceOrder(environment="廃坑の山村", value=3.0)


def _observation(body: str | TextWithPeople, route: object = OwnAction()) -> Observation:
    return Observation(
        body=body,
        route=route,
        time=_TIME,
        subject_is_self=True,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=True,
        order=_ORDER,
    )


def _choosing(memories: InMemoryShortTermMemoryRepository, clock: InMemoryMemoryTurnClock) -> None:
    memory = memories.get(GEN)
    memory.act(AgentMove(call_id="call_1", tool_name="give_item", arguments={}), current_turn=1)
    memories.save(memory)
    clock.advance_turn(GEN)


class TestReceiveActionTaken:
    """ReceiveActionTaken が、行動の返事と、その行為について本人が知った観測を、受け取ったときの呼び名で短期記憶に残すことを保証する。"""

    def test_people_in_the_summary_and_the_noticed_are_named_as_seen_when_received(self) -> None:
        """ゲンがサヨに鍵を渡そうとして断られると、要約も断りの観測も「サヨ」の呼び名で残り、行動のすぐ後に断りが並ぶ。"""
        memories = InMemoryShortTermMemoryRepository()
        clock = InMemoryMemoryTurnClock()
        _choosing(memories, clock)
        taken = ActionTaken(
            call_id="call_1",
            action_summary=TextWithPeople(template="「{target}」に「鍵」を渡そうとした", people={"target": SAYO}),
            accepted=False,
            time=_TIME,
            order=_ORDER,
        )
        noticed = _observation(TextWithPeople(template="{target}は手がふさがっている", people={"target": SAYO}))

        ReceiveActionTaken(memories, clock).execute(ReceiveActionTakenCommand(GEN, taken, noticed))

        assert recent_events_text(memories.get(GEN)) == (
            "- [1 日目 06:00] [行動] 「サヨ」に「鍵」を渡そうとした\n- [1 日目 06:00] サヨは手がふさがっている"
        )

    def test_without_anything_noticed_only_the_action_is_kept(self) -> None:
        """本人が知ったことが無ければ、行動の行だけが残る。"""
        memories = InMemoryShortTermMemoryRepository()
        clock = InMemoryMemoryTurnClock()
        _choosing(memories, clock)
        taken = ActionTaken(call_id="call_1", action_summary="待った", accepted=True, time=_TIME, order=_ORDER)

        ReceiveActionTaken(memories, clock).execute(ReceiveActionTakenCommand(GEN, taken))

        assert recent_events_text(memories.get(GEN)) == "- [1 日目 06:00] [行動] 待った"

    def test_noticed_through_another_route_is_rejected(self) -> None:
        """本人が知ったことを OwnAction 以外の経路で渡すと、コマンドを作る時点で ValueError を投げる。"""
        taken = ActionTaken(call_id="call_1", action_summary="待った", accepted=True, time=_TIME)

        with pytest.raises(ValueError, match="OwnAction"):
            ReceiveActionTakenCommand(GEN, taken, _observation("鐘が鳴った", route=SeenOrHeard()))
