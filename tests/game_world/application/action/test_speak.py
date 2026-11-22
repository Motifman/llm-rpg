from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone
from ai_rpg_world.game_world.domain.action.built_in_attempts import SpeechAttempt
from ai_rpg_world.game_world.domain.value_object import WorldTick
from ai_rpg_world.game_world.domain.world_records import PersonActedEvent
from tests.game_world.application.action.world_for_speech_and_ballot_tests import (
    HARU,
    WELL,
    WorldForSpeechAndBallots,
)


class TestSpeak:
    """Speak が、行っている最中でも話せて、話したことを行為として残すことを保証する。"""

    def test_speaking_notes_the_speech_as_an_act(self) -> None:
        """話すと ActionDone が返り、話した言葉を持つ PersonActedEvent が残る。"""
        world = WorldForSpeechAndBallots()

        reply = world.say(HARU, "井戸を見てくる")

        assert isinstance(reply, ActionDone)
        [acted] = [event for event in world.events() if isinstance(event, PersonActedEvent)]
        assert isinstance(acted.attempt, SpeechAttempt)
        assert acted.attempt.content.text == "井戸を見てくる"

    def test_person_on_the_way_can_speak(self) -> None:
        """移動していて Busy の人も話せ、ActionDone が返る。"""
        world = WorldForSpeechAndBallots()
        world.travel(HARU, WELL)

        reply = world.say(HARU, "先に行く")

        assert isinstance(reply, ActionDone)

    def test_speaking_on_the_way_keeps_the_travel_busy(self) -> None:
        """移動中 (梯子 3 tick) に話しても、行っているあいだは tick 3 まで残り、Busy のまま。"""
        world = WorldForSpeechAndBallots()
        world.travel(HARU, WELL)

        world.say(HARU, "先に行く")

        assert world.read().facts().vitals(HARU).is_busy(WorldTick(2)) is True
