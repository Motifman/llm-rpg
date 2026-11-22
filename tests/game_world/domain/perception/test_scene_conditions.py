from __future__ import annotations

import dataclasses

from ai_rpg_world.game_world.domain.declaration.spot import NoSmell
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_and_clock_time import DayAndClockTime
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.perception.scene_conditions import SceneConditions
from ai_rpg_world.game_world.domain.value_object import DescriptionText
from tests.game_world.domain.perception._surroundings_builders import conditions
from tests.game_world.support.world_design_for_tests import (
    clock_wording,
    half_hour_ticks_from_midnight,
    surroundings_texts,
    world_words,
)


def _lines(scene: SceneConditions) -> list[str]:
    return scene.lines(surroundings_texts().scene, world_words(), clock_wording())


class TestSceneConditionsLines:
    """SceneConditions.lines が、雰囲気・天候・時刻・時刻帯を、あるものだけ古い run の行の形で書くことを保証する。"""

    def test_quiet_indoor_place_without_clock_has_only_lighting_and_temperature(self) -> None:
        """音も匂いも無い屋内で昼夜の無い世界は、明るさと気温だけの雰囲気の 1 行になる。"""
        assert _lines(conditions(lighting=Lighting.DARK)) == ["雰囲気: 明るさ: 暗い / 気温: 過ごしやすい"]

    def test_sound_and_smell_join_the_atmosphere_in_the_old_order(self) -> None:
        """音と匂いがあると、明るさ・音・気温・匂いの順で雰囲気に並ぶ。"""
        scene = conditions()
        atmosphere = dataclasses.replace(
            scene.atmosphere, ambient_sound=DescriptionText("水の音"), smell=DescriptionText("油の匂い")
        )

        lines = _lines(dataclasses.replace(scene, atmosphere=atmosphere))

        assert lines == ["雰囲気: 明るさ: 明るい / 音: 水の音 / 気温: 過ごしやすい / 匂い: 油の匂い"]

    def test_weather_time_and_dark_phase_follow_the_atmosphere(self) -> None:
        """天候・時刻・暗い時刻帯があると、雰囲気のあとに天候、現在時刻、「(暗い)」つきの時刻帯が続く。"""
        night = dataclasses.replace(half_hour_ticks_from_midnight().phases[0], dark=True)
        scene = conditions(weather=WeatherType.SNOW, time=DayAndClockTime(day=1, hour=0, minute=30), phase=night)

        assert _lines(scene)[1:] == ["天候: snow（屋外）", "現在時刻: Day 1 深夜 0:30", "時刻帯: 昼 (暗い)"]

    def test_bright_phase_has_no_dark_mark(self) -> None:
        """暗くない時刻帯は「(暗い)」を付けずに書く。"""
        scene = conditions(phase=half_hour_ticks_from_midnight().phases[0])

        assert _lines(scene)[-1] == "時刻帯: 昼"

    def test_missing_smell_leaves_the_smell_part_out(self) -> None:
        """匂いが無いときは匂いの欄を出さない。"""
        scene = conditions()

        assert (
            "匂い"
            not in _lines(
                dataclasses.replace(scene, atmosphere=dataclasses.replace(scene.atmosphere, smell=NoSmell()))
            )[0]
        )
