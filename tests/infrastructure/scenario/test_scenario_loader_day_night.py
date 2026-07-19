"""ScenarioLoader の environment.day_night パース検証。

JSON → ScenarioDayNightConfig (DayNightCycleDef を含む) の往復と、
不正値での validation エラーを確認する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioDayNightConfig,
    ScenarioLoader,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    DayNightCycleValidationException,
    DayNightPhaseValidationException,
)


def _minimal_scenario(day_night_block: dict | None = None) -> dict:
    """最小限のシナリオ JSON 辞書 (graph や spot は省略可)。

    本テストは _parse_day_night_config のみを対象にするため、ロード可能な
    skeleton を組まずに直接 helper を呼ぶ。day_night_block を environment 下に
    入れた形を返すだけのヘルパ。
    """
    raw = {"environment": {}}
    if day_night_block is not None:
        raw["environment"]["day_night"] = day_night_block
    return raw


def _phases() -> list:
    return [
        {"name": "morning", "start_ratio": 0.0,
         "display_text": "朝", "ambient_light": 0.9, "is_dark": False},
        {"name": "evening", "start_ratio": 0.5,
         "display_text": "夕暮れ", "ambient_light": 0.5, "is_dark": False},
        {"name": "night", "start_ratio": 0.75,
         "display_text": "夜", "ambient_light": 0.1, "is_dark": True},
    ]


class TestParseDayNightConfig:
    """正常系: enabled / 省略 / 無効化の 3 パターン。"""

    def test_enabled_day_night_day_night_cycle_def(self) -> None:
        """JSON の phases が DayNightCycleDef.phases に正しく流し込まれる。"""
        loader = ScenarioLoader()
        env = _minimal_scenario({
            "enabled": True,
            "ticks_per_day": 24,
            "starting_tick_in_day": 6,
            "announce_changes": True,
            "phases": _phases(),
        })
        config = loader._parse_day_night_config(env["environment"])
        assert isinstance(config, ScenarioDayNightConfig)
        assert config.cycle.ticks_per_day == 24
        assert config.cycle.starting_tick_in_day == 6
        assert config.announce_changes is True
        assert len(config.cycle.phases) == 3
        assert config.cycle.phases[0].name == "morning"
        assert config.cycle.phases[2].is_dark is True

    def test_day_night_none(self) -> None:
        """environment.day_night を JSON に書かないシナリオは config=None。"""
        loader = ScenarioLoader()
        config = loader._parse_day_night_config({})
        assert config is None

    def test_enabled_false_none(self) -> None:
        """明示的に enabled=false にしたシナリオも昼夜サイクル無し扱い。"""
        loader = ScenarioLoader()
        env = _minimal_scenario({
            "enabled": False,
            "ticks_per_day": 12,
            "phases": _phases(),
        })
        config = loader._parse_day_night_config(env["environment"])
        assert config is None


class TestParseDayNightConfigValidation:
    """境界条件: 空フェーズ、不正な start_ratio、ticks_per_day=0 など。"""

    def test_phases_empty_scenario_load_error(self) -> None:
        """空配列は boundary で弾く (DayNightCycleDef まで届かない)。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError,
        )
        loader = ScenarioLoader()
        env = _minimal_scenario({
            "enabled": True,
            "ticks_per_day": 12,
            "phases": [],
        })
        with pytest.raises(ScenarioLoadError):
            loader._parse_day_night_config(env["environment"])

    def test_phases_start_ratio_day_night_cycle_validation(self) -> None:
        """DayNightCycleDef.__post_init__ で弾かれる (boundary 失敗)。"""
        loader = ScenarioLoader()
        env = _minimal_scenario({
            "enabled": True,
            "ticks_per_day": 12,
            "phases": [
                {"name": "a", "start_ratio": 0.0,
                 "display_text": "A", "ambient_light": 1.0, "is_dark": False},
                {"name": "b", "start_ratio": 0.7,
                 "display_text": "B", "ambient_light": 0.5, "is_dark": False},
                {"name": "c", "start_ratio": 0.3,  # 降順、不正
                 "display_text": "C", "ambient_light": 0.1, "is_dark": True},
            ],
        })
        with pytest.raises(DayNightCycleValidationException):
            loader._parse_day_night_config(env["environment"])

    def test_ticks_per_day_zero_day_night_cycle_validation(self) -> None:
        """ticks_per_day=0 はドメイン側の不変条件違反として弾かれる。"""
        loader = ScenarioLoader()
        env = _minimal_scenario({
            "enabled": True,
            "ticks_per_day": 0,
            "phases": _phases(),
        })
        with pytest.raises(DayNightCycleValidationException):
            loader._parse_day_night_config(env["environment"])

    def test_phases_element_dict_scenario_load_error(self) -> None:
        """配列要素が dict 以外なら boundary で弾く (KeyError 素通り防止)。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError,
        )
        loader = ScenarioLoader()
        env = _minimal_scenario({
            "enabled": True,
            "ticks_per_day": 12,
            "phases": ["not_a_dict"],
        })
        with pytest.raises(ScenarioLoadError):
            loader._parse_day_night_config(env["environment"])

    def test_phases_element_key_missing_scenario_load_error(self) -> None:
        """name / start_ratio / display_text / ambient_light / is_dark の欠落を boundary で弾く。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError,
        )
        loader = ScenarioLoader()
        env = _minimal_scenario({
            "enabled": True,
            "ticks_per_day": 12,
            "phases": [
                {"name": "incomplete", "start_ratio": 0.0},
                # display_text / ambient_light / is_dark 欠落
            ],
        })
        with pytest.raises(ScenarioLoadError):
            loader._parse_day_night_config(env["environment"])
