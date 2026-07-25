"""players[].objective / players[].goal_locked のパース検証 (目的層 G6)。

シナリオ JSON でプレイヤーごとの初期目的と改訂可否を宣言したとき、loader が
それを PlayerSpawnConfig に正しく載せること、未指定・空文字・不正型の扱いを
確認する。
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


def _player(**overrides) -> dict:
    base = {"id": "p1", "name": "P1", "spawn_spot": "room_a", "initial_items": []}
    base.update(overrides)
    return base


class TestPlayerObjectiveParsing:
    """JSON の players[].objective が PlayerSpawnConfig.objective に載る挙動を保証する。"""

    def test_objective_unspecified_becomes_none(self) -> None:
        """objective を書かなければ None になり、シナリオ共通目的への縮退を意味する。"""
        spawn = _load_first_spawn(_scenario_with_player(_player()))
        assert spawn.objective is None

    def test_objective_string_is_carried_through(self) -> None:
        """objective に書いた文字列がそのまま PlayerSpawnConfig に載る。"""
        spawn = _load_first_spawn(_scenario_with_player(
            _player(objective="救助ボートの席を確保する")
        ))
        assert spawn.objective == "救助ボートの席を確保する"

    def test_objective_inner_newlines_are_preserved(self) -> None:
        """前後の空白だけが削られ、箇条書きの内側の改行は保持される。"""
        spawn = _load_first_spawn(_scenario_with_player(
            _player(objective="\n- 狼煙を上げる\n- 仲間を見捨てない\n")
        ))
        assert spawn.objective == "- 狼煙を上げる\n- 仲間を見捨てない"

    def test_objective_blank_string_becomes_none(self) -> None:
        """空白のみの objective は None に畳まれ、未指定と同じ扱いになる。"""
        spawn = _load_first_spawn(_scenario_with_player(_player(objective="   \n ")))
        assert spawn.objective is None

    def test_objective_blank_string_is_warned(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """空白のみの objective は None に畳まれる際に警告が出て、痕跡が残る。"""
        with caplog.at_level("WARNING"):
            _load_first_spawn(_scenario_with_player(_player(objective="   \n ")))
        assert "p1" in caplog.text
        assert "objective" in caplog.text

    def test_objective_non_string_raises_with_player_id(self) -> None:
        """objective に文字列以外を渡すと ValueError を投げ、対象 player id を含む。"""
        with pytest.raises(ValueError) as exc_info:
            _load_first_spawn(_scenario_with_player(_player(objective=123)))
        assert "p1" in str(exc_info.value)
        assert "objective" in str(exc_info.value)


class TestPlayerGoalLockedParsing:
    """JSON の players[].goal_locked が PlayerSpawnConfig.goal_locked に載る挙動を保証する。"""

    def test_goal_locked_unspecified_becomes_none(self) -> None:
        """goal_locked を書かなければ None になり、シナリオ全体の性質からの導出を意味する。"""
        spawn = _load_first_spawn(_scenario_with_player(_player()))
        assert spawn.goal_locked is None

    def test_goal_locked_true_is_carried_through(self) -> None:
        """goal_locked に true を書くとそのまま True が載る。"""
        spawn = _load_first_spawn(_scenario_with_player(_player(goal_locked=True)))
        assert spawn.goal_locked is True

    def test_goal_locked_false_is_distinguished_from_unspecified(self) -> None:
        """goal_locked に false を書くと False が載り、未指定 (None) とは区別される。"""
        spawn = _load_first_spawn(_scenario_with_player(_player(goal_locked=False)))
        assert spawn.goal_locked is False

    def test_goal_locked_non_boolean_raises_with_player_id(self) -> None:
        """goal_locked に bool 以外を渡すと ValueError を投げ、対象 player id を含む。"""
        with pytest.raises(ValueError) as exc_info:
            _load_first_spawn(_scenario_with_player(_player(goal_locked="true")))
        assert "p1" in str(exc_info.value)
        assert "goal_locked" in str(exc_info.value)
