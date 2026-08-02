"""単独では正しい宣言が、機能の組合せとして成立することを保証する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable

import pytest

from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
    _DAY_NIGHT_FEATURE,
    _INTERACTION_CONDITION_FEATURE_REQUIREMENTS,
    _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS,
    _WEATHER_FEATURE,
)

_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    """変異対象のJSON objectを再帰的に返す。"""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _load_mutated(
    tmp_path: Path,
    source_name: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """実在シナリオを1点だけ壊し、通常のloader入口から読む。"""
    raw = json.loads((_SCENARIOS / source_name).read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / source_name
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    ScenarioLoader().load_from_file(path)


class TestScenarioFeatureConsistency:
    """機能を使う宣言と、その機能を成立させる世界設定の整合を検査する。"""

    def test_all_current_scenarios_are_consistent(self) -> None:
        """現行シナリオをglobで全件読み、検査の正の対照を固定する。"""
        paths = sorted(_SCENARIOS.glob("*.json"))
        assert paths
        for path in paths:
            ScenarioLoader().load_from_file(path)

    def test_every_interaction_condition_type_is_classified(self) -> None:
        """新しいinteraction条件は、必要な環境機能か非依存かを必ず宣言する。"""
        classified = set(_INTERACTION_CONDITION_FEATURE_REQUIREMENTS)
        known = set(InteractionConditionTypeEnum)

        assert classified == known, (
            f"未分類={sorted(c.value for c in known - classified)}, "
            f"廃止済み={sorted(c.value for c in classified - known)}"
        )

    def test_every_spawn_condition_key_is_classified(self) -> None:
        """spawn_conditionが受理する全キーは、必要な環境機能か非依存かを宣言する。"""
        assert _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS
        assert set(_MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS.values()) <= {
            None,
            _DAY_NIGHT_FEATURE,
            _WEATHER_FEATURE,
        }

    def test_unknown_spawn_condition_key_is_rejected(self, tmp_path: Path) -> None:
        """分類表に無いspawn_conditionキーは、黙って無視せず読み込み時に拒否する。"""
        def add_unknown_key(raw: dict[str, Any]) -> None:
            raw["monsters"]["initial_placements"][0]["spawn_condition"][
                "moon_phases"
            ] = ["full_moon"]

        with pytest.raises(ScenarioLoadError, match="moon_phases"):
            _load_mutated(
                tmp_path,
                "survival_island_v4_coop.json",
                add_unknown_key,
            )

    def test_zero_grace_rejects_exposed_tend_to_player(self, tmp_path: Path) -> None:
        """即死の世界でtend_to_playerが露出する宣言は、実行不能な手として拒否する。"""
        def expose_tending(raw: dict[str, Any]) -> None:
            raw["disabled_tools"].remove("tend_to_player")

        with pytest.raises(ScenarioLoadError, match="tend_to_player"):
            _load_mutated(tmp_path, "station_drill.json", expose_tending)

    def test_call_meeting_requires_an_enabled_meeting(self, tmp_path: Path) -> None:
        """CALL_MEETINGを置いた世界に会議宣言が無ければ、押しても進まないため拒否する。"""
        def remove_meeting(raw: dict[str, Any]) -> None:
            raw.pop("meeting")

        with pytest.raises(ScenarioLoadError, match="CALL_MEETING"):
            _load_mutated(tmp_path, "darkened_station.json", remove_meeting)

    def test_call_meeting_rejects_a_disabled_meeting(self, tmp_path: Path) -> None:
        """meeting宣言が存在しても無効なら、CALL_MEETINGを実行できないため拒否する。"""
        def disable_meeting(raw: dict[str, Any]) -> None:
            raw["meeting"]["enabled"] = False

        with pytest.raises(ScenarioLoadError, match="CALL_MEETING"):
            _load_mutated(tmp_path, "darkened_station.json", disable_meeting)

    def test_time_condition_requires_day_night(self, tmp_path: Path) -> None:
        """時間帯を読む条件に昼夜設定が無ければ、値が変化しないため拒否する。"""
        def remove_day_night(raw: dict[str, Any]) -> None:
            raw["environment"].pop("day_night")
            for node in _walk_dicts(raw):
                node.pop("day_night_phases", None)

        with pytest.raises(ScenarioLoadError, match="day_night"):
            _load_mutated(
                tmp_path,
                "survival_island_v4_coop.json",
                remove_day_night,
            )

    def test_day_night_spawn_condition_requires_day_night(
        self,
        tmp_path: Path,
    ) -> None:
        """出現条件のday_night_phasesにも昼夜設定が無ければ拒否する。"""
        def remove_day_night(raw: dict[str, Any]) -> None:
            raw["environment"].pop("day_night")

        with pytest.raises(ScenarioLoadError, match="day_night"):
            _load_mutated(tmp_path, "survival_island.json", remove_day_night)

    def test_weather_condition_requires_weather(self, tmp_path: Path) -> None:
        """天候を読む条件に天候設定が無ければ、値が変化しないため拒否する。"""
        def remove_weather(raw: dict[str, Any]) -> None:
            raw["environment"].pop("weather")

        with pytest.raises(ScenarioLoadError, match="weather"):
            _load_mutated(tmp_path, "weather_cascade_demo.json", remove_weather)

    def test_weather_condition_rejects_disabled_weather(self, tmp_path: Path) -> None:
        """天候設定が存在しても無効なら、天候条件の値が変化しないため拒否する。"""
        def disable_weather(raw: dict[str, Any]) -> None:
            raw["environment"]["weather"]["enabled"] = False

        with pytest.raises(ScenarioLoadError, match="weather"):
            _load_mutated(tmp_path, "weather_cascade_demo.json", disable_weather)

    def test_weather_spawn_condition_requires_weather(self, tmp_path: Path) -> None:
        """出現条件のweather_typesにも天候設定が無ければ拒否する。"""
        def remove_weather_and_other_weather_conditions(raw: dict[str, Any]) -> None:
            raw["environment"].pop("weather")
            for node in _walk_dicts(raw):
                if node.get("condition_type") in {"WEATHER_IS", "WEATHER_IS_NOT"}:
                    node["condition_type"] = "ALWAYS"
            raw["monsters"]["initial_placements"][0]["spawn_condition"][
                "weather_types"
            ] = ["STORM"]

        with pytest.raises(ScenarioLoadError, match="weather"):
            _load_mutated(
                tmp_path,
                "survival_island_v4_coop.json",
                remove_weather_and_other_weather_conditions,
            )
