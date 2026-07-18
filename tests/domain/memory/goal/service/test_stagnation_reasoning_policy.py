"""stagnation_reasoning_policy.resolve_stagnation_reasoning_effort が、停滞感 band と
reflect 注入の有無から熟考 effort を決める挙動を保証する。"""

from ai_rpg_world.domain.memory.goal.service.stagnation_reasoning_policy import (
    STAGNATION_REASONING_EFFORT,
    resolve_stagnation_reasoning_effort,
)


class TestResolveStagnationReasoningEffort:
    def test_strong_band_with_fresh_reflect_returns_effort(self) -> None:
        """band==strong かつ直前に停滞 reflect が注入された行動では、熟考 effort を返す。"""
        assert (
            resolve_stagnation_reasoning_effort("strong", fresh_reflect=True)
            == STAGNATION_REASONING_EFFORT
        )

    def test_strong_band_without_fresh_reflect_returns_none(self) -> None:
        """band==strong でも直前に reflect 注入が無ければ熟考しない (毎行動の連発を避ける)。"""
        assert resolve_stagnation_reasoning_effort("strong", fresh_reflect=False) is None

    def test_light_band_with_fresh_reflect_returns_none(self) -> None:
        """band==light は通常の難しさの範囲なので、reflect 注入直後でも熟考しない。"""
        assert resolve_stagnation_reasoning_effort("light", fresh_reflect=True) is None

    def test_none_band_returns_none(self) -> None:
        """停滞感なし (band==none) では熟考しない。"""
        assert resolve_stagnation_reasoning_effort("none", fresh_reflect=True) is None
