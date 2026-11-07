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
from ai_rpg_world.game_world.domain.rules.hunger_rule import (
    HungerLevel,
    HungerLevelName,
    HungerRule,
    NoStarvationDamage,
)
from ai_rpg_world.game_world.domain.value_object import Damage, HungerAmount


def _level(starts_at: int, name: str) -> HungerLevel:
    return HungerLevel(starts_at=HungerAmount(starts_at), name=HungerLevelName(name))


def _rule(
    levels: tuple[HungerLevel, ...],
    limit: int = 100,
    per_tick: int = 1,
    starvation_damage: Damage | NoStarvationDamage | None = None,
) -> HungerRule:
    return HungerRule(
        per_tick=HungerAmount(per_tick),
        limit=HungerAmount(limit),
        starvation_damage=NoStarvationDamage() if starvation_damage is None else starvation_damage,
        levels=levels,
    )


_LEVELS = (_level(0, "満腹"), _level(40, "小腹がすいた"), _level(80, "空腹"), _level(100, "飢えている"))


class TestHungerLevelName:
    """HungerLevelName が空でない呼び名だけを表すことを保証する。"""

    def test_name_keeps_the_declared_text(self) -> None:
        """宣言した呼び名をそのまま持つ。"""
        assert HungerLevelName("空腹").value == "空腹"

    @pytest.mark.parametrize("raw", ["", "  "])
    def test_blank_name_raises_domain_exception(self, raw: str) -> None:
        """空、または空白だけの呼び名は LevelNameBlankException を投げる。"""
        with pytest.raises(LevelNameBlankException):
            HungerLevelName(raw)


class TestHungerRuleLevelOf:
    """HungerRule.level_of が、空腹の量から宣言した境目どおりの段階を答えることを保証する。"""

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [(0, "満腹"), (39, "満腹"), (40, "小腹がすいた"), (79, "小腹がすいた"), (80, "空腹"), (100, "飢えている")],
    )
    def test_level_is_the_last_one_whose_boundary_is_reached(self, amount: int, expected: str) -> None:
        """量が境目に達した段階のうち、いちばん境目の大きい段階を答える (境目ちょうどはその段階に入る)。"""
        rule = _rule(_LEVELS)

        level = rule.level_of(HungerAmount(amount))

        assert level.name == HungerLevelName(expected)


class TestHungerRuleDeclaration:
    """HungerRule が、空腹の量が限界で止まる前提に合わない宣言を断り、飢えの痛手の有無を表すことを保証する。"""

    def test_no_levels_raises_domain_exception(self) -> None:
        """段階が 1 つも無いと NoLevelsDeclaredException を投げる。"""
        with pytest.raises(NoLevelsDeclaredException):
            _rule(())

    def test_first_boundary_above_zero_raises_domain_exception(self) -> None:
        """最初の段階の境目が 0 でないと LevelsNotStartingAtZeroException を投げる。"""
        with pytest.raises(LevelsNotStartingAtZeroException):
            _rule((_level(1, "小腹がすいた"),))

    def test_duplicated_boundary_raises_domain_exception(self) -> None:
        """同じ境目の段階が 2 つある (重なる) と LevelsNotAscendingException を投げる。"""
        with pytest.raises(LevelsNotAscendingException):
            _rule((_level(0, "満腹"), _level(80, "空腹"), _level(80, "飢えている")))

    def test_descending_boundaries_raise_domain_exception(self) -> None:
        """境目が昇順に並んでいないと LevelsNotAscendingException を投げる。"""
        with pytest.raises(LevelsNotAscendingException):
            _rule((_level(0, "満腹"), _level(80, "空腹"), _level(40, "小腹がすいた")))

    def test_duplicated_name_raises_domain_exception(self) -> None:
        """呼び名が同じ段階が 2 つあると LevelNameDuplicatedException を投げる。"""
        with pytest.raises(LevelNameDuplicatedException):
            _rule((_level(0, "空腹"), _level(80, "空腹")))

    def test_boundary_beyond_limit_raises_domain_exception(self) -> None:
        """境目が限界を超える段階は届かないので LevelBeyondLimitException を投げる。"""
        with pytest.raises(LevelBeyondLimitException):
            _rule((_level(0, "満腹"), _level(51, "飢えている")), limit=50)

    def test_limit_of_zero_raises_domain_exception(self) -> None:
        """限界 0 は最初から飢えている世界になるので RuleLimitBelowOneException を投げる。"""
        with pytest.raises(RuleLimitBelowOneException):
            _rule((_level(0, "満腹"),), limit=0)

    def test_per_tick_of_zero_is_accepted_for_a_world_without_hunger(self) -> None:
        """腹が減らない世界のため、per_tick 0 を受け付ける。"""
        rule = _rule(_LEVELS, per_tick=0)

        assert rule.per_tick == HungerAmount(0)

    def test_starvation_damage_distinguishes_a_world_without_damage(self) -> None:
        """限界のあいだの痛手は Damage で持ち、痛手の無い世界は NoStarvationDamage で別の値として持つ。"""
        harmful = _rule(_LEVELS, starvation_damage=Damage(5))
        harmless = _rule(_LEVELS, starvation_damage=NoStarvationDamage())

        assert harmful.starvation_damage == Damage(5)
        assert harmless.starvation_damage == NoStarvationDamage()
