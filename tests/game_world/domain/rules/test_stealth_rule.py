from __future__ import annotations

from collections.abc import Mapping

import pytest

from ai_rpg_world.game_world.domain.exception.rules_exception import MissingSightQualityException
from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SeesNothing, SeesShapes, SightQuality
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.value_object import Multiplier, Probability


def _chances(clearly: float, shapes: float, nothing: float) -> dict[SightQuality, Probability]:
    return {SeesClearly(): Probability(clearly), SeesShapes(): Probability(shapes), SeesNothing(): Probability(nothing)}


def _rule(
    by_bystander: Mapping[SightQuality, Probability] | None = None,
    by_target: Mapping[SightQuality, Probability] | None = None,
) -> StealthRule:
    return StealthRule(
        notice_by_bystander=_chances(0.4, 0.15, 0.0) if by_bystander is None else by_bystander,
        notice_by_target=_chances(0.6, 0.3, 0.0) if by_target is None else by_target,
        attentive_bonus=Probability(0.2),
        duration_multiplier=Multiplier(2.0),
    )


class TestStealthRule:
    """StealthRule が、見え方ごとに気づく確率をそろえて持ち、欠けた見え方を受け付けないことを保証する。"""

    def test_holds_declared_chances_bonus_and_multiplier(self) -> None:
        """見ていた人と相手の見え方ごとの確率、耳を澄ました人への上乗せ、行っているあいだの倍率を宣言どおりに持つ。"""
        rule = _rule()

        assert rule.notice_by_bystander[SeesShapes()] == Probability(0.15)
        assert rule.notice_by_target[SeesClearly()] == Probability(0.6)
        assert rule.attentive_bonus == Probability(0.2)
        assert rule.duration_multiplier == Multiplier(2.0)

    @pytest.mark.parametrize("missing", [SeesClearly(), SeesShapes(), SeesNothing()])
    def test_bystander_chances_lacking_a_sight_quality_are_refused(self, missing: SightQuality) -> None:
        """見ていた人の確率に見え方が 1 つでも欠けていると MissingSightQualityException を投げる。"""
        chances = {sight: chance for sight, chance in _chances(0.4, 0.15, 0.0).items() if sight != missing}

        with pytest.raises(MissingSightQualityException):
            _rule(by_bystander=chances)

    @pytest.mark.parametrize("missing", [SeesClearly(), SeesShapes(), SeesNothing()])
    def test_target_chances_lacking_a_sight_quality_are_refused(self, missing: SightQuality) -> None:
        """相手の確率に見え方が 1 つでも欠けていると MissingSightQualityException を投げる。"""
        chances = {sight: chance for sight, chance in _chances(0.6, 0.3, 0.0).items() if sight != missing}

        with pytest.raises(MissingSightQualityException):
            _rule(by_target=chances)

    def test_changing_the_passed_mapping_later_does_not_change_the_rule(self) -> None:
        """作ったあとに渡した dict を書き換えても、StealthRule の確率は変わらない。"""
        chances = _chances(0.4, 0.15, 0.0)
        rule = _rule(by_bystander=chances)

        chances[SeesClearly()] = Probability(1.0)

        assert rule.notice_by_bystander[SeesClearly()] == Probability(0.4)
