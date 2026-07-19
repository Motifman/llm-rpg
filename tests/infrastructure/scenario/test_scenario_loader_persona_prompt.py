"""PlayerSpawnConfig.persona_prompt のパース検証 (Phase E)。

JSON で players[].persona_prompt を宣言したとき、loader がそれを
PlayerSpawnConfig.persona_prompt に正しく載せること、空文字 / None /
非文字列の扱いを確認する。
"""

from __future__ import annotations

import copy

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


def _scenario_with_player(player_dict: dict) -> dict:
    """既存テストの最小シナリオを使って players だけ差し替える。"""
    from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["players"] = [player_dict]
    return scenario


def _load_first_spawn(scenario_dict: dict):
    result = ScenarioLoader().load_from_dict(scenario_dict)
    return result.player_spawns[0]


class TestPersonaPromptParsing:
    """JSON の persona_prompt が PlayerSpawnConfig に正しく載る。"""

    def test_persona_prompt_unspecified_none(self) -> None:
        """persona prompt 未指定なら None。"""
        spawn = _load_first_spawn(_scenario_with_player(
            {"id": "p1", "name": "P1", "spawn_spot": "room_a", "initial_items": []}
        ))
        assert spawn.persona_prompt is None

    def test_persona_prompt_string_included(self) -> None:
        """persona prompt 文字列がそのまま載る。"""
        spawn = _load_first_spawn(_scenario_with_player(
            {
                "id": "p1", "name": "P1", "spawn_spot": "room_a", "initial_items": [],
                "persona_prompt": "あなたはエイダ。医師。",
            }
        ))
        assert spawn.persona_prompt == "あなたはエイダ。医師。"

    def test_persona_prompt_around_blank_line_preserved(self) -> None:
        """persona prompt の前後空白は削られるが内側改行は保持される。"""
        spawn = _load_first_spawn(_scenario_with_player(
            {
                "id": "p1", "name": "P1", "spawn_spot": "room_a", "initial_items": [],
                "persona_prompt": "  あなたはエイダ。\n医師。  \n",
            }
        ))
        # 前後 strip、内側改行は保持 (多行プロンプトを許容する設計)
        assert spawn.persona_prompt == "あなたはエイダ。\n医師。"

    def test_empty_string_column_none(self) -> None:
        """空文字 / whitespace のみ → 「未設定」と同じ扱い。"""
        spawn = _load_first_spawn(_scenario_with_player(
            {
                "id": "p1", "name": "P1", "spawn_spot": "room_a", "initial_items": [],
                "persona_prompt": "   ",
            }
        ))
        assert spawn.persona_prompt is None


class TestPersonaPromptValidation:
    """型エラー (string 以外) は boundary で弾く。"""

    def test_case_raises_value_error(self) -> None:
        """数値は ValueError。"""
        with pytest.raises(ValueError, match="persona_prompt must be a string"):
            _load_first_spawn(_scenario_with_player(
                {
                    "id": "p1", "name": "P1", "spawn_spot": "room_a",
                    "initial_items": [], "persona_prompt": 42,
                }
            ))

    def test_list_raises_value_error(self) -> None:
        """list は ValueError。"""
        with pytest.raises(ValueError, match="persona_prompt must be a string"):
            _load_first_spawn(_scenario_with_player(
                {
                    "id": "p1", "name": "P1", "spawn_spot": "room_a",
                    "initial_items": [], "persona_prompt": ["bad"],
                }
            ))
