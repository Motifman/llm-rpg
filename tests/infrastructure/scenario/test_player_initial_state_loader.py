"""シナリオ JSON の `players[].initial_state` を `PlayerSpawnConfig.initial_state` に
正規化することを確認するテスト (Phase 4-D-2 PR 3)。

- 省略時は空 dict
- JSON プリミティブ (str / int / float / bool / None) は許容
- それ以外 (list / dict / 非 str キー) は `ScenarioLoadError` で load 時点拒否
"""

from __future__ import annotations

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


def _scenario_with_player(player_entry: dict) -> dict:
    """1 player + 任意の player entry を持つ最小シナリオ。"""
    base_player = {
        "id": "p",
        "name": "P",
        "spawn_spot": "s",
        "initial_items": [],
    }
    base_player.update(player_entry)
    return {
        "scenario_format_version": "1.0",
        "metadata": {
            "id": "x", "title": "x", "description": "x",
            "theme": "x", "difficulty": "easy", "estimated_ticks": 1,
            "author": "x", "tags": [],
        },
        "item_specs": [],
        "environment": {
            "weather": {
                "enabled": False,
                "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                "update_interval_ticks": 100, "announce_changes": False,
            },
        },
        "spots": [{
            "id": "s", "name": "S", "description": "d", "category": "OTHER",
            "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
            "interior": {"objects": []},
        }],
        "connections": [],
        "players": [base_player],
        "game_end_conditions": {"win": [], "lose": []},
    }


class TestPlayerInitialStateParsing:
    """`players[].initial_state` の各形式が `PlayerSpawnConfig.initial_state` に正規化される。"""

    def test_omitted_defaults_to_empty(self) -> None:
        """`initial_state` を省略すると空 dict (旧シナリオと互換)。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_player({}))
        assert result.player_spawns[0].initial_state == {}

    def test_explicit_empty_dict_is_accepted(self) -> None:
        """`initial_state: {}` は空 dict としてそのまま受け取る。"""
        result = ScenarioLoader().load_from_dict(
            _scenario_with_player({"initial_state": {}})
        )
        assert result.player_spawns[0].initial_state == {}

    def test_explicit_null_is_treated_as_empty(self) -> None:
        """`initial_state: null` は空 dict として扱う (JSON null 明示の互換)。"""
        result = ScenarioLoader().load_from_dict(
            _scenario_with_player({"initial_state": None})
        )
        assert result.player_spawns[0].initial_state == {}

    def test_primitive_values_are_preserved(self) -> None:
        """JSON プリミティブ (str / int / float / bool / None) はそのまま保持される。"""
        result = ScenarioLoader().load_from_dict(
            _scenario_with_player({
                "initial_state": {
                    "blessed": True,
                    "title": "巡礼者",
                    "level": 3,
                    "luck": 0.5,
                    "last_visited": None,
                },
            })
        )
        assert result.player_spawns[0].initial_state == {
            "blessed": True,
            "title": "巡礼者",
            "level": 3,
            "luck": 0.5,
            "last_visited": None,
        }


class TestPlayerInitialStateValidation:
    """`initial_state` の不正値は load 時点で `ScenarioLoadError` で拒否される。"""

    def test_non_dict_initial_state_rejected(self) -> None:
        """`initial_state` が dict でないと拒否。"""
        with pytest.raises(ScenarioLoadError, match="initial_state must be an object"):
            ScenarioLoader().load_from_dict(
                _scenario_with_player({"initial_state": "blessed=true"})
            )

    def test_nested_dict_value_rejected(self) -> None:
        """値に dict を入れるとプリミティブ違反として拒否 (flat dict 制約)。"""
        with pytest.raises(ScenarioLoadError, match="must be a JSON primitive"):
            ScenarioLoader().load_from_dict(
                _scenario_with_player({
                    "initial_state": {"buffs": {"blessed": True}},
                })
            )

    def test_list_value_rejected(self) -> None:
        """値に list を入れるとプリミティブ違反として拒否。"""
        with pytest.raises(ScenarioLoadError, match="must be a JSON primitive"):
            ScenarioLoader().load_from_dict(
                _scenario_with_player({
                    "initial_state": {"tags": ["pilgrim", "blessed"]},
                })
            )
