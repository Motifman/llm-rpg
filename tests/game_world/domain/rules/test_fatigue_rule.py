from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.rules_exception import (
    LevelBeyondLimitException,
    LevelNameBlankException,
    LevelNameDuplicatedException,
    LevelsNotAscendingException,
    LevelsNotStartingAtZeroException,
    NoLevelsDeclaredException,
    RuleLimitBelowOneException,
)
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueLevel, FatigueLevelName, FatigueRule
from ai_rpg_world.game_world.domain.value_object import FatigueAmount


def _level(starts_at: int, name: str) -> FatigueLevel:
    return FatigueLevel(starts_at=FatigueAmount(starts_at), name=FatigueLevelName(name))


def _rule(levels: tuple[FatigueLevel, ...], limit: int = 100, per_exertion: int = 2) -> FatigueRule:
    return FatigueRule(per_exertion=FatigueAmount(per_exertion), limit=FatigueAmount(limit), levels=levels)


_LEVELS = (_level(0, "元気"), _level(30, "疲れた"), _level(60, "へとへと"), _level(100, "動けない"))


class TestFatigueLevelName:
    """FatigueLevelName が空でない呼び名だけを表すことを保証する。"""

    def test_name_keeps_the_declared_text(self) -> None:
        """宣言した呼び名をそのまま持つ。"""
        assert FatigueLevelName("疲れた").value == "疲れた"

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_name_raises_domain_exception(self, raw: str) -> None:
        """空、または空白だけの呼び名は LevelNameBlankException を投げる。"""
        with pytest.raises(LevelNameBlankException):
            FatigueLevelName(raw)


class TestFatigueRuleLevelOf:
    """FatigueRule.level_of が、疲れの量から宣言した境目どおりの段階を答えることを保証する。"""

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            (0, "元気"),
            (29, "元気"),
            (30, "疲れた"),
            (59, "疲れた"),
            (60, "へとへと"),
            (99, "へとへと"),
            (100, "動けない"),
        ],
    )
    def test_level_is_the_last_one_whose_boundary_is_reached(self, amount: int, expected: str) -> None:
        """量が境目に達した段階のうち、いちばん境目の大きい段階を答える (境目ちょうどはその段階に入る)。"""
        rule = _rule(_LEVELS)

        level = rule.level_of(FatigueAmount(amount))

        assert level.name == FatigueLevelName(expected)

    def test_single_level_covers_every_amount(self) -> None:
        """境目 0 の段階が 1 つだけなら、どの量でもその段階を答える。"""
        rule = _rule((_level(0, "ふつう"),))

        assert rule.level_of(FatigueAmount(100)) == _level(0, "ふつう")


class TestFatigueRuleDeclaration:
    """FatigueRule が、疲れの量が限界で止まる前提に合わない宣言を断ることを保証する。"""

    def test_no_levels_raises_domain_exception(self) -> None:
        """段階が 1 つも無いと NoLevelsDeclaredException を投げる。"""
        with pytest.raises(NoLevelsDeclaredException):
            _rule(())

    def test_first_boundary_above_zero_raises_domain_exception(self) -> None:
        """最初の段階の境目が 0 でないと、段階の無い量ができるので LevelsNotStartingAtZeroException を投げる。"""
        with pytest.raises(LevelsNotStartingAtZeroException):
            _rule((_level(10, "疲れた"), _level(60, "へとへと")))

    def test_duplicated_boundary_raises_domain_exception(self) -> None:
        """同じ境目の段階が 2 つある (重なる) と LevelsNotAscendingException を投げる。"""
        with pytest.raises(LevelsNotAscendingException):
            _rule((_level(0, "元気"), _level(30, "疲れた"), _level(30, "へとへと")))

    def test_descending_boundaries_raise_domain_exception(self) -> None:
        """境目が昇順に並んでいないと LevelsNotAscendingException を投げる。"""
        with pytest.raises(LevelsNotAscendingException):
            _rule((_level(0, "元気"), _level(60, "へとへと"), _level(30, "疲れた")))

    def test_duplicated_name_raises_domain_exception(self) -> None:
        """呼び名が同じ段階が 2 つあると、段階の変化を見分けられないので LevelNameDuplicatedException を投げる。"""
        with pytest.raises(LevelNameDuplicatedException):
            _rule((_level(0, "疲れた"), _level(30, "疲れた")))

    def test_boundary_beyond_limit_raises_domain_exception(self) -> None:
        """境目が限界を超える段階は、量が限界で止まるので届かず、LevelBeyondLimitException を投げる。"""
        with pytest.raises(LevelBeyondLimitException):
            _rule((_level(0, "元気"), _level(101, "動けない")), limit=100)

    def test_boundary_equal_to_limit_is_accepted(self) -> None:
        """境目が限界と同じ段階は、限界に達したときの段階として受け付ける。"""
        rule = _rule((_level(0, "元気"), _level(100, "動けない")), limit=100)

        assert rule.level_of(FatigueAmount(100)) == _level(100, "動けない")

    def test_limit_of_zero_raises_domain_exception(self) -> None:
        """限界 0 は最初から限界に達した世界になるので RuleLimitBelowOneException を投げる。"""
        with pytest.raises(RuleLimitBelowOneException):
            _rule((_level(0, "元気"),), limit=0)

    def test_per_exertion_of_zero_is_accepted_for_a_world_without_fatigue(self) -> None:
        """体を使っても疲れない世界のため、per_exertion 0 を受け付ける。"""
        rule = _rule(_LEVELS, per_exertion=0)

        assert rule.per_exertion == FatigueAmount(0)
