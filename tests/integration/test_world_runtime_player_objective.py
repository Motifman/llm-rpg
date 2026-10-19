"""目的層 G6: プレイヤーごとの初期目的が world_runtime の【現在の目的】に効くことを固定。

- players[].objective を書いたプレイヤーには、その文が【現在の目的】に載る
- 書いていないプレイヤーには、シナリオ共通の llm_objective_text が載る
  (= 既存シナリオの挙動不変)
- 共通目的文が空でも全員に objective があれば起動でき、1 人でも欠けると
  fail-fast する

LLM は呼ばない。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import runtime_config

_BASE_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _write_scenario(tmp_path: Path, mutate) -> Path:
    """基底シナリオを読み、``mutate`` で書き換えたものを一時ファイルに書き出す。"""
    scenario = json.loads(_BASE_SCENARIO_PATH.read_text(encoding="utf-8"))
    mutate(scenario)
    path = tmp_path / "scenario_under_test.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    return path


def _runtime(path: Path):
    return create_world_runtime(path, config=runtime_config())


def _player_id_of(runtime, string_id: str) -> PlayerId:
    for spawn in runtime.scenario.player_spawns:
        if spawn.string_id == string_id:
            return PlayerId(spawn.player_id)
    raise AssertionError(f"player {string_id!r} not found in scenario")


def _current_objective_section(text: str) -> str:
    return f"【現在の目的】\n{text}\n\n"


def _user_content(runtime, player_id: PlayerId) -> str:
    return runtime.build_full_prompt(player_id)["messages"][1]["content"]


class TestPerPlayerObjective:
    """players[].objective がプレイヤーごとの【現在の目的】に載る挙動を保証する。"""

    def test_player_with_objective_sees_own_text(
        self, tmp_path: Path
    ) -> None:
        """objective を書いたプレイヤーの【現在の目的】には、その文が載る。"""
        def mutate(scenario: dict) -> None:
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"

        runtime = _runtime(_write_scenario(tmp_path, mutate))
        player_id = _player_id_of(runtime, "player_a")

        assert _current_objective_section("禁書を持ち出して 1 人で逃げる") in _user_content(
            runtime, player_id
        )

    def test_player_without_objective_falls_back_to_scenario_text(
        self, tmp_path: Path
    ) -> None:
        """objective を書かないプレイヤーの【現在の目的】には、シナリオ共通の目的文が載る。"""
        def mutate(scenario: dict) -> None:
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"

        runtime = _runtime(_write_scenario(tmp_path, mutate))
        player_id = _player_id_of(runtime, "player_b")
        scenario_text = runtime._resolve_scenario_llm_objective_text()

        assert _current_objective_section(scenario_text) in _user_content(runtime, player_id)

    def test_two_players_can_hold_different_objectives(self, tmp_path: Path) -> None:
        """同じ run の 2 人に別々の目的文が載り、互いに混ざらない。"""
        def mutate(scenario: dict) -> None:
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"
            scenario["players"][1]["objective"] = "禁書を書架に戻して封印する"

        runtime = _runtime(_write_scenario(tmp_path, mutate))

        user_a = _user_content(runtime, _player_id_of(runtime, "player_a"))
        user_b = _user_content(runtime, _player_id_of(runtime, "player_b"))
        assert _current_objective_section("禁書を持ち出して 1 人で逃げる") in user_a
        assert _current_objective_section("禁書を書架に戻して封印する") in user_b
        assert "禁書を書架に戻して封印する" not in user_a
        assert "禁書を持ち出して 1 人で逃げる" not in user_b

    def test_unmodified_scenario_shows_scenario_text_to_everyone(
        self, tmp_path: Path
    ) -> None:
        """objective を 1 つも書かない既存シナリオでは、全員の【現在の目的】に共通目的文が載る (挙動不変)。"""
        runtime = _runtime(_write_scenario(tmp_path, lambda scenario: None))
        scenario_text = runtime._resolve_scenario_llm_objective_text()

        for string_id in ("player_a", "player_b"):
            player_id = _player_id_of(runtime, string_id)
            assert _current_objective_section(scenario_text) in _user_content(runtime, player_id)


class TestUnknownPlayerFallback:
    """player_spawns に無い player_id で目的解決が呼ばれたときの縮退挙動を保証する。

    現行の呼び出し元はすべて player_spawns 由来なので通常は到達しないが、
    将来 spawn と独立した player_id 生成経路が増えたときに「黙って他人の目的が
    渡る」回帰を検知するために固定する。
    """

    def test_unknown_player_falls_back_to_scenario_text_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """未知の player_id では共通目的文へ縮退し、その旨が warning に残る。"""
        def mutate(scenario: dict) -> None:
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"

        runtime = _runtime(_write_scenario(tmp_path, mutate))
        scenario_text = runtime._resolve_scenario_llm_objective_text()

        with caplog.at_level("WARNING"):
            resolved = runtime._resolve_player_objective_text(
                PlayerId(9999), scenario_text
            )

        assert resolved == scenario_text
        assert "9999" in caplog.text


class TestObjectiveFailFast:
    """共通目的文が空のときの fail-fast が、個別目的の有無で切り替わる挙動を保証する。"""

    def test_empty_scenario_text_is_allowed_when_every_player_has_objective(
        self, tmp_path: Path
    ) -> None:
        """共通目的文が空でも全員に objective があれば起動でき、各自の目的が載る。"""
        def mutate(scenario: dict) -> None:
            scenario["metadata"]["llm_objective_text"] = ""
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"
            scenario["players"][1]["objective"] = "禁書を書架に戻して封印する"

        runtime = _runtime(_write_scenario(tmp_path, mutate))

        assert runtime._resolve_scenario_llm_objective_text() == ""
        user_a = _user_content(runtime, _player_id_of(runtime, "player_a"))
        assert _current_objective_section("禁書を持ち出して 1 人で逃げる") in user_a

    def test_empty_scenario_text_raises_when_one_player_lacks_objective(
        self, tmp_path: Path
    ) -> None:
        """共通目的文が空で objective を欠くプレイヤーが 1 人でもいると、その id を含む例外になる。"""
        def mutate(scenario: dict) -> None:
            scenario["metadata"]["llm_objective_text"] = ""
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"

        runtime = _runtime(_write_scenario(tmp_path, mutate))

        with pytest.raises(ValueError) as exc_info:
            runtime._resolve_scenario_llm_objective_text()
        assert "player_b" in str(exc_info.value)
