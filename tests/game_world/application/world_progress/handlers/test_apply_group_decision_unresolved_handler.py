from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import GroupDecisionUnresolved
from ai_rpg_world.game_world.domain.effect.flag_effects import RaiseFlagEffect
from tests.game_world.application.world_progress.handlers.group_decision_world import (
    AKI,
    EXILE,
    EXILED,
    STALLED,
    exile_vote_world,
    haru_votes_for,
    raised,
)


class TestApplyGroupDecisionUnresolvedHandler:
    """集団の決定が決まらなかったときに、when_undecided の効果を当てる挙動を保証する。"""

    def test_effect_of_unresolved_decision_applies(self) -> None:
        """アキがナツに、ハルがアキに入れて同数で決まらないと、when_undecided で決まらなかった旗が立ち、そのきっかけは GroupDecisionUnresolved。"""
        world, raised_by = exile_vote_world(
            when_decided=RaiseFlagEffect(EXILED), when_undecided=RaiseFlagEffect(STALLED)
        )

        world.scope.run(haru_votes_for(AKI))

        assert (world.read(raised(EXILED)), world.read(raised(STALLED))) == (False, True)
        assert raised_by.triggers == [GroupDecisionUnresolved(EXILE)]
