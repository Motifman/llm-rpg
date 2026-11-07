from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.lighting_exception import InvalidLightingConditionsException
from ai_rpg_world.game_world.domain.lighting import Lighting, LightingConditions


def _conditions(
    declared: Lighting,
    *,
    outdoor: bool = False,
    dark_time_of_day: bool = False,
    weather_obscures: bool = False,
    light_source_present: bool = False,
) -> LightingConditions:
    return LightingConditions(
        declared=declared,
        outdoor=outdoor,
        dark_time_of_day=dark_time_of_day,
        weather_obscures=weather_obscures,
        light_source_present=light_source_present,
    )


class TestDeclaredLighting:
    """暗くする材料も光源も無いとき、LightingConditions.lighting が場所の宣言をそのまま返すことを保証する。"""

    @pytest.mark.parametrize("declared", list(Lighting))
    def test_without_any_modifier_returns_the_declared_lighting(self, declared: Lighting) -> None:
        """屋内で、暗い時間帯でも悪天候でもなく、光源も無ければ、宣言の明るさのまま。"""
        assert _conditions(declared).lighting() is declared


class TestDarkeningOutdoors:
    """屋外で暗い時間帯か見えにくくする天候のとき、明るさが 1 段だけ暗くなることを保証する。"""

    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            (Lighting.BRIGHT, Lighting.DUSKY),
            (Lighting.DUSKY, Lighting.DARK),
            (Lighting.DARK, Lighting.PITCH_DARK),
            (Lighting.PITCH_DARK, Lighting.PITCH_DARK),
        ],
    )
    def test_outdoor_dark_time_of_day_darkens_one_step(self, declared: Lighting, expected: Lighting) -> None:
        """屋外で暗い時間帯なら 1 段暗くなる。真っ暗はそれ以上暗くならない。"""
        assert _conditions(declared, outdoor=True, dark_time_of_day=True).lighting() is expected

    def test_outdoor_obscuring_weather_darkens_one_step(self) -> None:
        """屋外で見えにくくする天候なら、明るい時間帯でも 1 段暗くなる。"""
        assert _conditions(Lighting.BRIGHT, outdoor=True, weather_obscures=True).lighting() is Lighting.DUSKY

    def test_dark_time_and_obscuring_weather_together_darken_only_one_step(self) -> None:
        """暗い時間帯と見えにくくする天候が重なっても、2 段ではなく 1 段だけ暗くなる。"""
        conditions = _conditions(Lighting.BRIGHT, outdoor=True, dark_time_of_day=True, weather_obscures=True)

        assert conditions.lighting() is Lighting.DUSKY

    @pytest.mark.parametrize(
        ("dark_time_of_day", "weather_obscures"),
        [(True, False), (False, True), (True, True)],
    )
    def test_indoors_neither_dark_time_nor_weather_darkens(
        self, dark_time_of_day: bool, weather_obscures: bool
    ) -> None:
        """屋内なら、暗い時間帯でも見えにくくする天候でも宣言の明るさのまま。"""
        conditions = _conditions(
            Lighting.BRIGHT, outdoor=False, dark_time_of_day=dark_time_of_day, weather_obscures=weather_obscures
        )

        assert conditions.lighting() is Lighting.BRIGHT


class TestLightSource:
    """灯った光源を手に持つ人がいるとき、暗い・真っ暗だけが薄暗いへ上がることを保証する。"""

    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            (Lighting.BRIGHT, Lighting.BRIGHT),
            (Lighting.DUSKY, Lighting.DUSKY),
            (Lighting.DARK, Lighting.DUSKY),
            (Lighting.PITCH_DARK, Lighting.DUSKY),
        ],
    )
    def test_light_source_lifts_dark_and_pitch_dark_to_dusky(self, declared: Lighting, expected: Lighting) -> None:
        """光源があると、暗い・真っ暗は薄暗いになり、明るい・薄暗いはそのまま。"""
        assert _conditions(declared, light_source_present=True).lighting() is expected

    def test_light_source_applies_after_darkening(self) -> None:
        """宣言が薄暗い屋外の夜は暗いまで下がるが、光源があれば薄暗いへ戻る (暗くしてから光源を当てる)。"""
        conditions = _conditions(Lighting.DUSKY, outdoor=True, dark_time_of_day=True, light_source_present=True)

        assert conditions.lighting() is Lighting.DUSKY

    def test_light_source_lifts_pitch_dark_outdoor_night_to_dusky(self) -> None:
        """宣言が真っ暗の屋外の夜は真っ暗のままだが、光源があれば薄暗いになる。"""
        conditions = _conditions(Lighting.PITCH_DARK, outdoor=True, dark_time_of_day=True, light_source_present=True)

        assert conditions.lighting() is Lighting.DUSKY

    def test_light_source_does_not_undo_darkening_of_bright(self) -> None:
        """宣言が明るい屋外の夜は薄暗いへ下がり、光源があっても明るいへは戻らない。"""
        conditions = _conditions(Lighting.BRIGHT, outdoor=True, dark_time_of_day=True, light_source_present=True)

        assert conditions.lighting() is Lighting.DUSKY


class TestLightingConditionsValidation:
    """材料の型を取り違えた LightingConditions を作れないことを保証する。"""

    def test_declared_must_be_a_lighting(self) -> None:
        """declared に Lighting でない値 (文字列の "DARK") を渡すと InvalidLightingConditionsException を投げる。"""
        with pytest.raises(InvalidLightingConditionsException):
            _conditions("DARK")  # type: ignore[arg-type]

    @pytest.mark.parametrize("field", ["outdoor", "dark_time_of_day", "weather_obscures", "light_source_present"])
    @pytest.mark.parametrize("raw", [1, "false", None])
    def test_flags_must_be_bool(self, field: str, raw: object) -> None:
        """真偽の材料に bool でない値 (1、文字列の "false"、None) を渡すと InvalidLightingConditionsException を投げる。"""
        with pytest.raises(InvalidLightingConditionsException):
            _conditions(Lighting.BRIGHT, **{field: raw})  # type: ignore[arg-type]
