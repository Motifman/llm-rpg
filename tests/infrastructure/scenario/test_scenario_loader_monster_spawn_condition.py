"""ScenarioLoader._parse_monster_spawn_condition の検証 (Phase B-2b)。

spawn_condition ブロックを ScenarioMonsterSpawnCondition に変換する経路と、
不正値の boundary 検証。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
    ScenarioMonsterSpawnCondition,
)


class TestParseMonsterSpawnCondition:
    """spawn_condition の正常系と境界系。"""

    def test_None_は_None_を返す(self) -> None:
        """spawn_condition セクション未宣言は static placement (= None)。"""
        loader = ScenarioLoader()
        result = loader._parse_monster_spawn_condition(None, 0)
        assert result is None

    def test_day_night_phases_を文字列タプルに変換(self) -> None:
        loader = ScenarioLoader()
        result = loader._parse_monster_spawn_condition(
            {"day_night_phases": ["night", "evening"]}, 0,
        )
        assert isinstance(result, ScenarioMonsterSpawnCondition)
        assert result.day_night_phase_names == ("night", "evening")
        assert result.is_always is False

    def test_required_と_forbidden_flags_を保持(self) -> None:
        loader = ScenarioLoader()
        result = loader._parse_monster_spawn_condition(
            {
                "required_flags": ["high_tide"],
                "forbidden_flags": ["storm_warned"],
            },
            0,
        )
        assert result.required_flags == ("high_tide",)
        assert result.forbidden_flags == ("storm_warned",)

    def test_weather_types_の不正値は_ScenarioLoadError(self) -> None:
        """WeatherTypeEnum に無い名前は boundary で弾く。"""
        loader = ScenarioLoader()
        with pytest.raises(ScenarioLoadError) as exc:
            loader._parse_monster_spawn_condition(
                {"weather_types": ["TYPHOON"]}, 0,
            )
        # エラーメッセージに valid な enum 値が含まれる
        assert "weather_types" in str(exc.value)

    def test_全軸が空なら_is_always_True(self) -> None:
        loader = ScenarioLoader()
        result = loader._parse_monster_spawn_condition({}, 0)
        assert result is not None
        assert result.is_always is True

    def test_配列でない値は_ScenarioLoadError(self) -> None:
        loader = ScenarioLoader()
        with pytest.raises(ScenarioLoadError):
            loader._parse_monster_spawn_condition(
                {"day_night_phases": "night"}, 0,  # 文字列、list ではない
            )

    def test_dict_でない_spawn_condition_は_ScenarioLoadError(self) -> None:
        loader = ScenarioLoader()
        with pytest.raises(ScenarioLoadError):
            loader._parse_monster_spawn_condition("night", 0)
