"""resolve_stagnation_pressure_band の境界値を保証する (P-U2)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.memory.goal.service.stagnation_pressure_band import (
    STAGNATION_PRESSURE_BAND_LIGHT,
    STAGNATION_PRESSURE_BAND_NONE,
    STAGNATION_PRESSURE_BAND_STRONG,
    resolve_stagnation_pressure_band,
)


class TestResolveStagnationPressureBand:
    """カウンタ値から表出バンドへの写像の境界値を確認する。"""

    def test_zero_count_resolves_to_none_band(self) -> None:
        """カウンタが 0 のとき、停滞感なし (none) を返す。"""
        assert resolve_stagnation_pressure_band(0) == STAGNATION_PRESSURE_BAND_NONE

    @pytest.mark.parametrize("count", [1, 2])
    def test_light_range_resolves_to_light_band(self, count: int) -> None:
        """カウンタが 1〜2 のとき、軽い停滞感 (light) を返す。"""
        assert resolve_stagnation_pressure_band(count) == STAGNATION_PRESSURE_BAND_LIGHT

    @pytest.mark.parametrize("count", [3, 4, 10])
    def test_strong_range_resolves_to_strong_band(self, count: int) -> None:
        """カウンタが 3 以上のとき、強い停滞感 (strong) を返す。"""
        assert resolve_stagnation_pressure_band(count) == STAGNATION_PRESSURE_BAND_STRONG

    def test_negative_count_raises_value_error(self) -> None:
        """負のカウンタは不変条件違反として ValueError を投げる。"""
        with pytest.raises(ValueError):
            resolve_stagnation_pressure_band(-1)

    def test_non_int_count_raises_type_error(self) -> None:
        """int でないカウンタは TypeError を投げる。"""
        with pytest.raises(TypeError):
            resolve_stagnation_pressure_band(1.5)  # type: ignore[arg-type]
