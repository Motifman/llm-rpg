"""夜 / 悪天候による屋外 spot の視界減衰 (PR3: 視界減衰)。

設計:
- 屋外スポットは夜 or 悪天候で lighting を 1 段下げる
- 屋内スポットは空の影響を受けない (元の atmosphere lighting を維持)
- 夜 + 悪天候の同時発生でも 1 段だけ下げる (上限あり)
- 光源持ちは DARK/PITCH_BLACK を DIM に引き上げる (既存ロジック維持)
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.service.spot_perception_service import (
    SpotPerceptionService,
)
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere


def _atm(lighting: LightingEnum) -> SpotAtmosphere:
    """テスト用に lighting だけ指定した SpotAtmosphere を作る。"""
    from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
    return SpotAtmosphere(
        lighting=lighting,
        sound_ambient="",
        temperature=TemperatureEnum.NORMAL,
        smell="",
    )


class TestBackwardCompat:
    """既存呼び出し (kwarg 省略) は従来挙動を維持。"""

    def test_kwarg_省略時は_従来挙動(self) -> None:
        svc = SpotPerceptionService()
        # 屋外/夜/悪天候の各 kwarg を省略 = default False
        # → 屋外でも夜でも悪天候でもないものとして扱う
        result = svc.compute_effective_lighting(_atm(LightingEnum.BRIGHT), False)
        assert result is LightingEnum.BRIGHT

    def test_DARK_な_spot_は_光源持ちで_DIM_に引き上げ(self) -> None:
        """既存挙動: 光源持ちは PITCH_BLACK/DARK を DIM にする。"""
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.DARK), spot_has_any_light_bearer=True,
        )
        assert result is LightingEnum.DIM


class TestOutdoorNight:
    """屋外スポットは夜になると 1 段暗くなる。"""

    def test_屋外_BRIGHT_は_夜に_DIM_になる(self) -> None:
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.BRIGHT), False,
            is_outdoor=True, time_of_day_is_dark=True,
        )
        assert result is LightingEnum.DIM

    def test_屋外_DIM_は_夜に_DARK_になる(self) -> None:
        """森の中など元から DIM な屋外スポットは夜で DARK に。"""
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.DIM), False,
            is_outdoor=True, time_of_day_is_dark=True,
        )
        assert result is LightingEnum.DARK

    def test_屋外_DARK_は_夜に_PITCH_BLACK_になる(self) -> None:
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.DARK), False,
            is_outdoor=True, time_of_day_is_dark=True,
        )
        assert result is LightingEnum.PITCH_BLACK


class TestIndoorNight:
    """屋内スポットは空の影響を受けない (夜でも元のまま)。"""

    def test_屋内_BRIGHT_は_夜でも_BRIGHT(self) -> None:
        """屋内で BRIGHT (例えば焚き火が点いている部屋) は夜でも明るい。"""
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.BRIGHT), False,
            is_outdoor=False, time_of_day_is_dark=True,
        )
        assert result is LightingEnum.BRIGHT

    def test_屋内_DARK_は_夜でも_DARK_のまま(self) -> None:
        """洞窟は元から DARK で、夜という概念に影響されない。"""
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.DARK), False,
            is_outdoor=False, time_of_day_is_dark=True,
        )
        assert result is LightingEnum.DARK


class TestWeatherObscuresVision:
    """嵐 / 濃霧で屋外の視界が下がる。"""

    def test_屋外_嵐で_BRIGHT_は_DIM_になる(self) -> None:
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.BRIGHT), False,
            is_outdoor=True, weather_obscures_vision=True,
        )
        assert result is LightingEnum.DIM

    def test_屋内_は_天候の影響を受けない(self) -> None:
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.BRIGHT), False,
            is_outdoor=False, weather_obscures_vision=True,
        )
        assert result is LightingEnum.BRIGHT


class TestNightAndWeatherCombo:
    """夜と悪天候が両立しても 1 段だけ下げる (重複しない)。"""

    def test_夜_and_嵐_は_1_段だけ下がる(self) -> None:
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.BRIGHT), False,
            is_outdoor=True, time_of_day_is_dark=True, weather_obscures_vision=True,
        )
        # BRIGHT → DIM (1 段)。DARK にはならない
        assert result is LightingEnum.DIM


class TestLightBearerInteraction:
    """光源持ちは夜の DARK 化後にも DIM 引き上げが効く。"""

    def test_夜の屋外_DIM_は_光源持ちで_DIM_に引き上げ(self) -> None:
        """森が夜で DARK になっても、誰かが松明を持っていれば DIM (見える)。"""
        svc = SpotPerceptionService()
        result = svc.compute_effective_lighting(
            _atm(LightingEnum.DIM), spot_has_any_light_bearer=True,
            is_outdoor=True, time_of_day_is_dark=True,
        )
        # DIM → 夜 → DARK → 光源で → DIM
        assert result is LightingEnum.DIM
