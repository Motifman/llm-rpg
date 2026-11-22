from __future__ import annotations

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.connectives import AllOfCondition, AnyOfCondition
from ai_rpg_world.game_world.domain.condition.person_conditions import AllOutcomesDecidedCondition
from ai_rpg_world.game_world.domain.condition.world_time_conditions import (
    TickAtLeastCondition,
    TicksInWorldStageAtLeastCondition,
    TimeOfDayIsCondition,
)
from ai_rpg_world.game_world.domain.declaration.verb.ending_declaration import EndingDeclaration
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldTick
from tests.game_world.support.world_design_for_tests import half_hour_ticks_from_midnight


def _all_decided() -> AllOutcomesDecidedCondition:
    return AllOutcomesDecidedCondition(failure_text=NoText())


class TestHasDeadline:
    """EndingDeclaration.has_deadline が、結末の条件が世界の時刻 (何 tick 目か) を読むかで締め切りの有無を決めることを保証する。"""

    def test_ending_by_outcomes_alone_has_no_deadline(self) -> None:
        """全員の結末が決まったら終わる世界 (山村 v2) には締め切りが無い。"""
        assert not EndingDeclaration(ends_when=_all_decided()).has_deadline()

    def test_ending_at_a_tick_has_a_deadline(self) -> None:
        """何 tick 目に達したら終わる、を「または」で含む世界には締め切りがある。"""
        ends_when = AnyOfCondition(
            children=(_all_decided(), TickAtLeastCondition(tick=WorldTick(40), failure_text=NoText())),
            failure_text=NoText(),
        )

        assert EndingDeclaration(ends_when=ends_when).has_deadline()

    def test_ending_after_ticks_in_a_stage_has_a_deadline(self) -> None:
        """段階に入ってから何 tick 経ったら終わる世界にも締め切りがある。"""
        ends_when = AllOfCondition(
            children=(TicksInWorldStageAtLeastCondition(ticks=Ticks(10), failure_text=NoText()),),
            failure_text=NoText(),
        )

        assert EndingDeclaration(ends_when=ends_when).has_deadline()

    def test_ending_at_a_time_of_day_has_no_deadline(self) -> None:
        """時刻帯 (朝になったら) で終わる条件は、行動の総量の締め切りとして数えない。"""
        phase = half_hour_ticks_from_midnight().phases[0].name

        ends_when = TimeOfDayIsCondition(phase=phase, failure_text=NoText())

        assert not EndingDeclaration(ends_when=ends_when).has_deadline()
