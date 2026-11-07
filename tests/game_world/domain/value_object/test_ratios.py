from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object import Multiplier, Probability, Rate


class TestRate:
    """Rate が 0 以上 1 以下の割合 (TendRule.revive_hp_rate の 0.6 など) だけを表すことを保証する。"""

    @pytest.mark.parametrize("raw", [0, 0.6, 1, 1.0])
    def test_values_from_zero_to_one_are_accepted(self, raw: float) -> None:
        """0、0.6、1 を受け付ける (整数でも小数でもよい)。"""
        assert Rate(raw) == Rate(raw)

    @pytest.mark.parametrize("raw", [-0.01, 1.01, 2.0])
    def test_values_outside_zero_to_one_raise_domain_exception(self, raw: float) -> None:
        """0 未満か 1 を超える値は ValueOutOfRangeException を投げる (倍率は Multiplier で表す)。"""
        with pytest.raises(ValueOutOfRangeException):
            Rate(raw)

    @pytest.mark.parametrize("raw", [True, "0.5", float("nan")])
    def test_non_numbers_raise_domain_exception(self, raw: object) -> None:
        """数でない値 (真偽値、文字列、NaN) は ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Rate(raw)  # type: ignore[arg-type]


class TestMultiplier:
    """Multiplier が 0 より大きい倍率 (StealthRule.duration_rate の 2 倍など) だけを表すことを保証する。"""

    @pytest.mark.parametrize("raw", [0.5, 1, 2, 2.5])
    def test_positive_values_are_accepted(self, raw: float) -> None:
        """1 未満も 1 を超える値も、0 より大きければ受け付ける。"""
        assert Multiplier(raw) == Multiplier(raw)

    @pytest.mark.parametrize("raw", [0, -1.0])
    def test_zero_or_negative_raises_domain_exception(self, raw: float) -> None:
        """0 や負の倍率は ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Multiplier(raw)

    @pytest.mark.parametrize("raw", [True, float("inf"), float("nan")])
    def test_non_finite_or_non_numbers_raise_domain_exception(self, raw: object) -> None:
        """真偽値、無限大、NaN は ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Multiplier(raw)  # type: ignore[arg-type]


class TestProbability:
    """Probability が 0 以上 1 以下の確率だけを表し、足すと 1 で止まることを保証する。"""

    @pytest.mark.parametrize("raw", [0, 0.15, 1])
    def test_values_from_zero_to_one_are_accepted(self, raw: float) -> None:
        """0、0.15、1 を受け付ける。"""
        assert Probability(raw) == Probability(raw)

    @pytest.mark.parametrize("raw", [-0.1, 1.1])
    def test_values_outside_zero_to_one_raise_domain_exception(self, raw: float) -> None:
        """0 未満か 1 を超える値は ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Probability(raw)

    @pytest.mark.parametrize("raw", [False, float("nan")])
    def test_non_numbers_raise_domain_exception(self, raw: object) -> None:
        """真偽値と NaN は ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            Probability(raw)  # type: ignore[arg-type]

    def test_adding_a_bonus_sums_the_probabilities(self) -> None:
        """気づく確率 40% に、耳を澄ましている人の 20% を足すと 60% になる (StealthRule.attentive_bonus)。"""
        # 確率は float で持つので、0.4 + 0.2 は 0.6 ちょうどにならない。
        assert (Probability(0.4) + Probability(0.2)).value == pytest.approx(0.6)

    def test_adding_beyond_one_stops_at_one(self) -> None:
        """90% に 20% を足すと、1 を超えずに 100% で止まる。"""
        assert Probability(0.9) + Probability(0.2) == Probability(1)
