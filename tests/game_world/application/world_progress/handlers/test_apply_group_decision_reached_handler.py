from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import GroupDecisionResult
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect, SequenceEffect
from ai_rpg_world.game_world.domain.effect.flag_effects import RaiseFlagEffect
from tests.game_world.application.world_progress.handlers.group_decision_world import (
    EXILE,
    EXILED,
    NATSU,
    STALLED,
    START_ROLL_CALL,
    exile_is_open,
    exile_vote_world,
    haru_votes_for,
    raised,
)


class TestApplyGroupDecisionReachedHandler:
    """集団の決定が決まったときに、when_decided の効果を選ばれた人とともに当てる挙動を保証する。"""

    def test_effect_of_reached_decision_applies_with_the_chosen_person(self) -> None:
        """アキに続いてハルもナツに入れて決まると、when_decided で追放の旗が立ち、そのきっかけはナツを選んだ GroupDecisionResult。"""
        world, raised_by = exile_vote_world(
            when_decided=RaiseFlagEffect(EXILED), when_undecided=RaiseFlagEffect(STALLED)
        )

        world.scope.run(haru_votes_for(NATSU))

        assert (world.read(raised(EXILED)), world.read(raised(STALLED))) == (True, False)
        assert raised_by.triggers == [GroupDecisionResult(EXILE, chosen=NATSU)]

    def test_refused_effect_rolls_back_only_the_handler_and_keeps_the_ballot(self) -> None:
        """when_decided が追放の旗を立ててから開いている点呼を始め直そうとして断られると、追放の旗は立たず、ハルの票で決まった投票は閉じたまま残り、断りが 1 つ数えられる。"""
        world, _ = exile_vote_world(
            when_decided=SequenceEffect(steps=(RaiseFlagEffect(EXILED), START_ROLL_CALL)), when_undecided=NoEffect()
        )

        world.scope.run(haru_votes_for(NATSU))

        assert (world.read(raised(EXILED)), world.read(exile_is_open)) == (False, False)
        assert world.distributor.refused_handlers == {
            ("ApplyGroupDecisionReachedHandler", "GAME_WORLD.GROUP_DECISION_ALREADY_OPEN"): 1
        }
