"""目的層 G6: プレイヤーごとの初期目的と改訂可否が world_runtime に効くことを固定。

- players[].objective を書いたプレイヤーはその文で goal store に seed される
- 書いていないプレイヤーはシナリオ共通の llm_objective_text で seed される
  (= 既存シナリオの挙動不変)
- players[].goal_locked はシナリオ全体から導出した locked を上書きする
- 共通目的文が空でも全員に objective があれば起動でき、1 人でも欠けると
  fail-fast する

LLM は呼ばない。goal store は既定 OFF なので明示的に ON にする。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import episodic_config

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
    return create_world_runtime(path, config=episodic_config(goal_store_enabled=True))


def _player_id_of(runtime, string_id: str) -> PlayerId:
    for spawn in runtime.scenario.player_spawns:
        if spawn.string_id == string_id:
            return PlayerId(spawn.player_id)
    raise AssertionError(f"player {string_id!r} not found in scenario")


def _seeded_goal_text(runtime, player_id: PlayerId) -> str:
    """【現在の目的】の描画を 1 度走らせ、seed された目的文を返す。"""
    scenario_text = runtime._resolve_scenario_llm_objective_text()
    fallback = runtime._resolve_player_objective_text(player_id, scenario_text)
    return runtime._resolve_objective_via_goal_store(player_id, fallback)


def _seeded_goal_entry(runtime, player_id: PlayerId):
    being_id = runtime.aux_being_resolver.resolve_being_id(
        runtime.aux_being_default_world_id, player_id
    )
    return runtime._goal_journal_store.get_active_by_being(being_id)


class TestPerPlayerObjectiveSeeding:
    """players[].objective がプレイヤーごとの初期目的として goal store に届く挙動を保証する。"""

    def test_player_with_objective_is_seeded_with_own_text(
        self, tmp_path: Path
    ) -> None:
        """objective を書いたプレイヤーは、その文で goal store に seed される。"""
        def mutate(scenario: dict) -> None:
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"

        runtime = _runtime(_write_scenario(tmp_path, mutate))
        player_id = _player_id_of(runtime, "player_a")

        assert _seeded_goal_text(runtime, player_id) == "禁書を持ち出して 1 人で逃げる"
        assert _seeded_goal_entry(runtime, player_id).text == "禁書を持ち出して 1 人で逃げる"

    def test_player_without_objective_falls_back_to_scenario_text(
        self, tmp_path: Path
    ) -> None:
        """objective を書かないプレイヤーはシナリオ共通の目的文で seed される。"""
        def mutate(scenario: dict) -> None:
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"

        runtime = _runtime(_write_scenario(tmp_path, mutate))
        player_id = _player_id_of(runtime, "player_b")
        scenario_text = runtime._resolve_scenario_llm_objective_text()

        assert _seeded_goal_text(runtime, player_id) == scenario_text

    def test_two_players_can_hold_different_objectives(self, tmp_path: Path) -> None:
        """同じ run の 2 人が別々の目的文で seed され、互いに混ざらない。"""
        def mutate(scenario: dict) -> None:
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"
            scenario["players"][1]["objective"] = "禁書を書架に戻して封印する"

        runtime = _runtime(_write_scenario(tmp_path, mutate))

        text_a = _seeded_goal_text(runtime, _player_id_of(runtime, "player_a"))
        text_b = _seeded_goal_text(runtime, _player_id_of(runtime, "player_b"))
        assert text_a == "禁書を持ち出して 1 人で逃げる"
        assert text_b == "禁書を書架に戻して封印する"

    def test_unmodified_scenario_seeds_scenario_text_for_everyone(
        self, tmp_path: Path
    ) -> None:
        """objective を 1 つも書かない既存シナリオでは全員が共通目的文で seed される (挙動不変)。"""
        runtime = _runtime(_write_scenario(tmp_path, lambda scenario: None))
        scenario_text = runtime._resolve_scenario_llm_objective_text()

        for string_id in ("player_a", "player_b"):
            player_id = _player_id_of(runtime, string_id)
            assert _seeded_goal_text(runtime, player_id) == scenario_text


class TestPerPlayerGoalLocked:
    """players[].goal_locked がシナリオ由来の locked を上書きする挙動を保証する。"""

    def test_locked_defaults_to_scenario_derived_value(self, tmp_path: Path) -> None:
        """goal_locked 未指定なら、勝敗条件を持つシナリオでは locked=True で seed される。"""
        runtime = _runtime(_write_scenario(tmp_path, lambda scenario: None))
        player_id = _player_id_of(runtime, "player_a")
        _seeded_goal_text(runtime, player_id)

        assert _seeded_goal_entry(runtime, player_id).locked is True

    def test_goal_locked_false_unlocks_a_single_player(self, tmp_path: Path) -> None:
        """勝敗条件つきシナリオでも goal_locked=false のプレイヤーだけ locked=False で seed される。"""
        def mutate(scenario: dict) -> None:
            scenario["players"][0]["goal_locked"] = False

        runtime = _runtime(_write_scenario(tmp_path, mutate))

        unlocked = _player_id_of(runtime, "player_a")
        still_locked = _player_id_of(runtime, "player_b")
        _seeded_goal_text(runtime, unlocked)
        _seeded_goal_text(runtime, still_locked)

        assert _seeded_goal_entry(runtime, unlocked).locked is False
        assert _seeded_goal_entry(runtime, still_locked).locked is True


class TestUnknownPlayerFallback:
    """player_spawns に無い player_id で目的解決が呼ばれたときの縮退挙動を保証する。

    現行の呼び出し元はすべて player_spawns 由来なので通常は到達しないが、
    将来 spawn と独立した player_id 生成経路が増えたときに「黙って他人の目的で
    seed される」回帰を検知するために固定する。
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

    def test_unknown_player_goal_locked_falls_back_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """未知の player_id では locked がシナリオ由来の値へ縮退し、warning が残る。"""
        runtime = _runtime(_write_scenario(tmp_path, lambda scenario: None))

        with caplog.at_level("WARNING"):
            locked = runtime._resolve_player_goal_locked(PlayerId(9999))

        assert locked is True  # 勝敗条件を持つシナリオなので従来どおり locked
        assert "9999" in caplog.text


class TestObjectiveFailFast:
    """共通目的文が空のときの fail-fast が、個別目的の有無で切り替わる挙動を保証する。"""

    def test_empty_scenario_text_is_allowed_when_every_player_has_objective(
        self, tmp_path: Path
    ) -> None:
        """共通目的文が空でも全員に objective があれば起動でき、各自の目的で seed される。"""
        def mutate(scenario: dict) -> None:
            scenario["metadata"]["llm_objective_text"] = ""
            scenario["players"][0]["objective"] = "禁書を持ち出して 1 人で逃げる"
            scenario["players"][1]["objective"] = "禁書を書架に戻して封印する"

        runtime = _runtime(_write_scenario(tmp_path, mutate))

        assert runtime._resolve_scenario_llm_objective_text() == ""
        text_a = _seeded_goal_text(runtime, _player_id_of(runtime, "player_a"))
        assert text_a == "禁書を持ち出して 1 人で逃げる"

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
