from __future__ import annotations

from ai_rpg_world.game_world.domain.condition.chance_condition import ChanceCondition
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.connectives import NotCondition
from ai_rpg_world.game_world.domain.condition.flag_conditions import FlagIsRaisedCondition
from ai_rpg_world.game_world.domain.condition.settling_occasion import SettlingOccasion
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId
from ai_rpg_world.game_world.domain.value_object.probability import Probability

_BELL = FlagDeclaration(FlagId("bell"), DescriptionText("鐘が鳴った"), initially_raised=False)
_GUST = ChanceCondition(Probability(0.5), NoText())
_BELL_RANG = FlagIsRaisedCondition(flag=_BELL, failure_text=NoText())


class TestSettlingOccasion:
    """SettlingOccasion.checks が、確率を使う条件を時間を進めたときだけ確かめる決まりを保証する。"""

    def test_after_world_time_passed_checks_a_chance_condition(self) -> None:
        """時間を進めたあとの落ち着かせでは、確率を使う条件も確かめる。"""
        assert SettlingOccasion.AFTER_WORLD_TIME_PASSED.checks(_GUST) is True

    def test_after_command_skips_a_chance_condition(self) -> None:
        """コマンドのあとの落ち着かせでは、確率を使う条件を確かめない。1 tick にくじを何度も引かないため。"""
        assert SettlingOccasion.AFTER_COMMAND.checks(_GUST) is False

    def test_after_command_skips_a_condition_with_chance_nested_inside(self) -> None:
        """確率を使う条件を否定で包んでも、コマンドのあとの落ち着かせでは確かめない。"""
        assert SettlingOccasion.AFTER_COMMAND.checks(NotCondition(_GUST, NoText())) is False

    def test_after_command_checks_a_condition_without_chance(self) -> None:
        """確率を使わない条件 (旗が立っている) は、コマンドのあとの落ち着かせでも確かめる。"""
        assert SettlingOccasion.AFTER_COMMAND.checks(_BELL_RANG) is True
