from __future__ import annotations

import pytest

from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.application.action.enter_section import EnterSectionCommand
from ai_rpg_world.game_world.domain.action.action_refusal import WorldStateRefusal
from ai_rpg_world.game_world.domain.action.built_in_attempts import EnterSectionAttempt
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.exception.whereabouts_exception import SectionFullException
from ai_rpg_world.game_world.domain.people import TextAboutPeople, TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId
from tests.game_world.application.world_for_accepting_tests import (
    ALICE,
    BELL,
    BOB,
    CAGE,
    GEN,
    GUST,
    WORLD_ENDED,
    WORLD_ENDED_TEXT,
    WorldForAccepting,
)


class TestActionsInArrivalOrder:
    """選んだ行為を取るとき、届いた行為を 1 つずつ確定させ、先に届いたほうから通すことを保証する。"""

    @pytest.mark.parametrize(("first", "second"), [(ALICE, BOB), (BOB, ALICE)])
    def test_first_arrival_takes_last_seat(self, first: PersonId, second: PersonId) -> None:
        """定員 1 の籠に 2 人が続けて乗り込もうとすると、先に届いた人が乗り、後の人は SECTION_FULL で断られる。"""
        world = WorldForAccepting()

        first_reply = world.board_cage(first)
        second_reply = world.board_cage(second)

        assert isinstance(first_reply, ActionDone)
        assert isinstance(second_reply, ActionRefused)
        assert second_reply.refusal.reason == WorldStateRefusal(RefusalCode(SectionFullException.error_code))
        assert (world.in_cage(first), world.in_cage(second)) == (True, False)


class TestActionsSettleWorldConditions:
    """選んだ行為を取るとき、行為のあとに、コマンドのあとの落ち着かせを回すことを保証する。断られた行為のあとも回す。"""

    def test_happening_fires_after_action_meets_its_condition(self) -> None:
        """アリスが籠に乗ると、「アリスが籠にいる」で鳴る鐘の出来事が発火し、偶然で吹く風の出来事は発火しない。"""
        world = WorldForAccepting()

        world.board_cage(ALICE)

        assert (world.is_raised(BELL), world.is_raised(GUST)) == (True, False)

    def test_world_conditions_settle_after_refused_action(self) -> None:
        """落ち着かせを通さずにアリスを籠に乗せたあと、ボブの乗り込みが満員で断られると、そのあとの落ち着かせで鐘が鳴る。"""
        world = WorldForAccepting()
        attempt = EnterSectionAttempt(ALICE, world.design.section_access(CAGE.section_id))
        world.enter_section_without_settling(EnterSectionCommand(attempt))
        assert world.is_raised(BELL) is False

        reply = world.board_cage(BOB)

        assert isinstance(reply, ActionRefused)
        assert world.is_raised(BELL) is True


class TestActionsAfterWorldEnded:
    """世界が終わったあとに届いた行為は、行為を確定させる取引の中で断られ、世界を変えないことを保証する。"""

    def test_action_after_world_ended_is_refused_with_world_ended_text(self) -> None:
        """世界が終わったあとにゲンが籠に乗ろうとすると、WORLD_ALREADY_ENDED の理由と「世界はもう終わった。」の文で断られる。"""
        world = WorldForAccepting()
        world.end_world()

        reply = world.board_cage(GEN)

        assert isinstance(reply, ActionRefused)
        assert reply.refusal.reason == WorldStateRefusal(WORLD_ENDED)
        assert reply.refusal.text == TextAboutPeople(TextWithUnassignedPeople(WORLD_ENDED_TEXT), {})

    def test_action_after_world_ended_replies_with_the_text_and_summary_of_the_refusal(self) -> None:
        """世界が終わったあとにゲンが籠に乗ろうとして断られると、返事の結末は「世界はもう終わった。」の文と、籠に乗り込む要約を持つ。"""
        world = WorldForAccepting()
        world.end_world()

        reply = world.board_cage(GEN)

        assert isinstance(reply, ActionRefused)
        assert reply.outcome.result == TextAboutPeople(TextWithUnassignedPeople(WORLD_ENDED_TEXT), {})
        assert reply.outcome.summary == TextWithUnassignedPeople("enter_sectionした cage").about({})

    def test_action_after_world_ended_changes_nothing(self) -> None:
        """世界が終わったあとのアリスの乗り込みは、アリスを籠に入れず、鐘も鳴らさず、断られた試みのイベントも含めて何も配らない。"""
        world = WorldForAccepting()
        world.end_world()

        world.board_cage(ALICE)

        assert (world.in_cage(ALICE), world.is_raised(BELL)) == (False, False)
        assert world.events == []


class TestSettlingAfterWorldEnded:
    """SettleWorldConditions が、世界が終わったあとには、条件が真の出来事を発火させないことを保証する。反応と二人で合わせる操作は同じ取引の頭で断られるが、ここでは出来事だけを見る。"""

    def test_happening_whose_condition_holds_does_not_fire_after_world_ended(self) -> None:
        """落ち着かせを通さずにアリスを籠に乗せ、世界を終わらせてから落ち着かせると、「アリスが籠にいる」で鳴る鐘は鳴らず、何も配られない。"""
        world = WorldForAccepting()
        attempt = EnterSectionAttempt(ALICE, world.design.section_access(CAGE.section_id))
        world.enter_section_without_settling(EnterSectionCommand(attempt))
        world.end_world()

        world.settle_after_command()

        assert world.is_raised(BELL) is False
        assert world.events == []
