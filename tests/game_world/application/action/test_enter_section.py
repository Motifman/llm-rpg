from __future__ import annotations

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.domain.action.action_refusal import PreconditionRefusal, WorldStateRefusal
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import SectionFullException
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from tests.game_world.application.action.world_for_action_tests import (
    ALICE,
    BOB,
    CAGE,
    GATE_CLOSED_TEXT,
    LOFT,
    WorldForActions,
)


class TestEnterSection:
    """EnterSection が、区画の出入りの宣言に従って行う人を区画に入れ、満員なら断ることを保証する。"""

    def test_actor_enters_section(self) -> None:
        """空いている区画に入ると ActionDone が返り、行う人はその区画の中にいる。"""
        world = WorldForActions()

        reply = world.enter_cage(ALICE)

        assert isinstance(reply, ActionDone)
        assert world.read().facts().whereabouts().is_in_section(PersonBody(ALICE), CAGE) is True

    def test_done_reply_uses_the_authors_enter_text_and_the_section_name(self) -> None:
        """区画 cage に入ると、返事の本人向けの文は、共通の部品の文ではなく、作者が区画の出入りに書いた「乗り込んだ。」になる。"""
        world = WorldForActions()

        reply = world.enter_cage(ALICE)

        assert isinstance(reply, ActionDone)
        assert reply.outcome.result == TextAboutPeople(TextWithUnassignedPeople("乗り込んだ。"), {})
        assert reply.outcome.summary.template == TextWithUnassignedPeople("enter_sectionした cage")

    def test_full_section_refuses_with_section_full_code(self) -> None:
        """定員 1 の区画に誰かがいると、次の人は SECTION_FULL の RefusalCode で断られ、区画の外に残る。"""
        world = WorldForActions()
        world.enter_cage(ALICE)

        reply = world.enter_cage(BOB)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(RefusalCode(SectionFullException.error_code))
        assert world.read().facts().whereabouts().is_in_section(PersonBody(BOB), CAGE) is False

    def test_unmet_entry_condition_refuses_with_its_failure_text(self) -> None:
        """入る条件が偽の区画に入ろうとすると、その条件の failure_text を持つ PreconditionRefusal で断られ、区画の外に残る。"""
        world = WorldForActions()

        reply = world.enter(ALICE, LOFT)

        assert isinstance(reply, ActionRefused)
        assert isinstance(reply.refusal.reason, PreconditionRefusal)
        assert reply.refusal.text == TextAboutPeople(TextWithUnassignedPeople(GATE_CLOSED_TEXT), {})
        assert world.read().facts().whereabouts().is_in_section(PersonBody(ALICE), LOFT) is False
