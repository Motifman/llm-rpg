from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone
from ai_rpg_world.game_world.application.world_has_ended import WorldHasEnded, WorldHasEndedCommand
from tests.game_world.application.world_for_accepting_tests import ALICE, ALICE_IN_CAGE, WorldForAccepting


class TestWorldHasEnded:
    """WorldHasEnded が、外側に世界が終わったかどうかを答えることを保証する。"""

    def test_answers_false_before_world_ends(self) -> None:
        """開いたばかりの世界について問うと、偽が返る。"""
        world = WorldForAccepting()

        assert WorldHasEnded(world.scope)(WorldHasEndedCommand()) is False

    def test_answers_true_after_world_ends(self) -> None:
        """世界を終わらせたあとに問うと、真が返る。"""
        world = WorldForAccepting()
        world.end_world()

        assert WorldHasEnded(world.scope)(WorldHasEndedCommand()) is True

    def test_action_that_ends_world_replies_done_and_world_has_ended_answers_true(self) -> None:
        """「アリスが籠にいる」で終わる世界でアリスが籠に乗ると、返事は ActionDone のままで、そのあと問うと真が返る。"""
        world = WorldForAccepting(ends_when=ALICE_IN_CAGE)

        reply = world.board_cage(ALICE)

        assert isinstance(reply, ActionDone)
        assert WorldHasEnded(world.scope)(WorldHasEndedCommand()) is True
