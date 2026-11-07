from __future__ import annotations

from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.tend_rule import NoTending, TendRule
from ai_rpg_world.game_world.domain.value_object import Rate, Ticks


class TestTendRule:
    """介抱の決まりが、介抱のある世界と無い世界を別の値で表すことを保証する。"""

    def test_tend_rule_holds_the_rate_of_hit_points_on_revival(self) -> None:
        """TendRule は、起こしたときの体力の割合 (既定の 0.6) を Rate で持つ。"""
        rule = TendRule(revive_hp_rate=Rate(0.6))

        assert rule.revive_hp_rate == Rate(0.6)

    def test_no_tending_is_a_different_value_from_any_tend_rule(self) -> None:
        """介抱の無い世界 (NoTending) は、どの割合の TendRule とも等しくない。"""
        assert NoTending() != TendRule(revive_hp_rate=Rate(0.0))
        assert NoTending() == NoTending()


class TestDeathRule:
    """DeathRule が、倒れてから死ぬまでの猶予を Ticks で持つことを保証する。"""

    def test_grace_of_zero_is_accepted_for_dying_on_falling(self) -> None:
        """猶予 0 (倒れたらすぐ死ぬ世界) を受け付ける。"""
        assert DeathRule(grace=Ticks(0)).grace == Ticks(0)

    def test_grace_holds_the_declared_ticks(self) -> None:
        """既定の 30 tick の猶予をそのまま持つ。"""
        assert DeathRule(grace=Ticks(30)).grace == Ticks(30)
