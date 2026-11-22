from __future__ import annotations

import dataclasses

import pytest

from ai_rpg_world.game_world.domain.declaration.spot.temperature import Temperature
from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SCENE_LINE_NAMES, SceneTexts
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.exception.surroundings_texts_exception import (
    MissingWorldWordException,
    UnfillableSceneTextException,
)
from ai_rpg_world.game_world.domain.lighting import Lighting
from tests.game_world.support.world_design_for_tests import scene_texts, world_words


class TestWorldWords:
    """WorldWords が、明るさ・気温・天候のすべてに言葉があることを作るときに確かめることを保証する。"""

    @pytest.mark.parametrize(
        ("field", "missing"),
        [("lighting", Lighting.DARK), ("temperature", Temperature.HOT), ("weather", WeatherType.FOG)],
    )
    def test_missing_word_is_refused(self, field: str, missing: object) -> None:
        """どれか 1 つに言葉が無いと、MissingWorldWordException を投げる。"""
        words = dict(getattr(world_words(), field))
        del words[missing]

        with pytest.raises(MissingWorldWordException):
            dataclasses.replace(world_words(), **{field: words})

    def test_blank_word_is_refused(self) -> None:
        """空白だけの言葉は、無いのと同じく MissingWorldWordException を投げる。"""
        words = dict(world_words().weather) | {WeatherType.SNOW: " "}

        with pytest.raises(MissingWorldWordException):
            dataclasses.replace(world_words(), weather=words)


class TestSceneTexts:
    """SceneTexts が、書けない場面の行の言い回しを作るときに断ることを保証する。"""

    @pytest.mark.parametrize("field", ["atmosphere", "destination", "impassable", "object", "clock"])
    def test_unknown_name_in_a_line_is_refused(self, field: str) -> None:
        """行の言い回しに埋められない名前があると、UnfillableSceneTextException を投げる。"""
        fields: dict[str, object] = {field: "{unknown}"}

        with pytest.raises(UnfillableSceneTextException):
            dataclasses.replace(scene_texts(), **fields)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("field", "text"),
        [
            ("destination", '  - "{passage}"（{status}）'),
            ("weather", "天候: 晴れ"),
            ("object", '  - "{object}" — {description}'),
        ],
    )
    def test_line_that_forgets_a_value_is_refused(self, field: str, text: str) -> None:
        """埋めるべき値 (行き先の名前、天候、見た目) を書き忘れた言い回しは、UnfillableSceneTextException を投げる。"""
        fields: dict[str, object] = {field: text}

        with pytest.raises(UnfillableSceneTextException):
            dataclasses.replace(scene_texts(), **fields)  # type: ignore[arg-type]

    def test_every_line_field_is_checked(self) -> None:
        """言い回しの欄は、宣言の文 (見出し・品物・数の印・真っ暗の文) を除いて、すべて検証の一覧に載っている。"""
        declared_words = {"heading", "ground_items", "count_mark", "pitch_dark"}

        assert set(SCENE_LINE_NAMES) == {field.name for field in dataclasses.fields(SceneTexts)} - declared_words

    def test_reaching_into_a_value_is_refused(self) -> None:
        """値の属性を読もうとする言い回しは、素の例外ではなく UnfillableSceneTextException を投げる。"""
        with pytest.raises(UnfillableSceneTextException):
            dataclasses.replace(scene_texts(), destination="{spot.name}")
