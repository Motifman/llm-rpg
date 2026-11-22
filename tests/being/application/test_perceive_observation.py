from __future__ import annotations

import dataclasses

from ai_rpg_world.being.application.perceive_observation import PerceiveObservation, PerceiveObservationCommand
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, PersonInText, SeenOrHeard, TextWithPeople
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.short_term_memory import Perception
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)

GEN = BeingId("gen")
DOOR_BROKE = Observation(
    body="扉が壊れた",
    route=SeenOrHeard(),
    time=ObservedTime(display="tick 3"),
    subject_is_self=False,
    subject_name=UNKNOWN,
    source=UNKNOWN,
    place=UNKNOWN,
    addressed_to_self=UNKNOWN,
)


class TestPerceiveObservation:
    """PerceiveObservation が、観測を Being の短期記憶に、次のターンが見る出来事として入れて保存することを保証する。"""

    def test_observation_is_saved_at_the_current_turn(self) -> None:
        """記憶のターンが 2 のとき「扉が壊れた」を受け取ると、短期記憶に、次のターン 3 の知覚として 1 件だけ保存される。"""
        memories = InMemoryShortTermMemoryRepository()
        clock = InMemoryMemoryTurnClock()
        clock.advance_turn(GEN)
        clock.advance_turn(GEN)

        PerceiveObservation(memories, clock).execute(PerceiveObservationCommand(being_id=GEN, observation=DOOR_BROKE))

        [experience] = memories.get(GEN).experiences
        assert isinstance(experience, Perception)
        assert (experience.observation, experience.turn) == (DOOR_BROKE, 3)

    def test_people_in_the_body_are_named_as_seen_when_received(self) -> None:
        """「{actor}が扉を開けた」の actor が名前の見えるサヨと、名前の見えない背の高い男のとき、短期記憶にはそれぞれ「サヨが扉を開けた」「背の高い男が扉を開けた」で入る。"""
        memories = InMemoryShortTermMemoryRepository()
        perceive = PerceiveObservation(memories, InMemoryMemoryTurnClock())

        for person in (
            PersonInText(handle=1, appearance="髪を結った娘", visible_name="サヨ"),
            PersonInText(handle=2, appearance="背の高い男", visible_name=None),
        ):
            body = TextWithPeople(template="{actor}が扉を開けた", people={"actor": person})
            perceive.execute(
                PerceiveObservationCommand(being_id=GEN, observation=dataclasses.replace(DOOR_BROKE, body=body))
            )

        bodies = [e.observation.body for e in memories.get(GEN).experiences if isinstance(e, Perception)]
        assert bodies == ["サヨが扉を開けた", "背の高い男が扉を開けた"]
