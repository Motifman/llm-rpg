from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import OccupantNotInSectionException
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from tests.game_world.application.action.world_for_action_tests import ALICE, CAGE, WorldForActions


class TestLeaveSection:
    """LeaveSection が、区画の中にいる人を区画から出し、区画にいない人の試みを断ることを保証する。"""

    def test_actor_in_section_leaves_it(self) -> None:
        """区画に入って行っているあいだが過ぎた人が出ると ActionDone が返り、区画の外にいる。"""
        world = WorldForActions()
        world.enter_cage(ALICE)
        world.pass_ticks(1)

        reply = world.leave_cage(ALICE)

        assert isinstance(reply, ActionDone)
        assert world.read().facts().whereabouts().is_in_section(PersonBody(ALICE), CAGE) is False

    def test_actor_not_in_section_is_refused(self) -> None:
        """区画にいない人が出ようとすると、OCCUPANT_NOT_IN_SECTION の RefusalCode で断られる。"""
        world = WorldForActions()

        reply = world.leave_cage(ALICE)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(OccupantNotInSectionException.error_code))
