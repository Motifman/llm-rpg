"""P5 (目的層 G1): world_runtime を通した goal store の配線と「挙動不変」を固定。

- flag OFF (既定): goal store は構築されず、【現在の目的】は従来どおり
  scenario.metadata.llm_objective_text の静的文字列
- flag ON: goal store が構築され、初回描画でシナリオ目的が
  locked=True / origin=scenario で seed される。**描画結果は静的文字列と同一**
  (質感テストの本命 = 既存シナリオの挙動不変)

LLM は呼ばない。flag は default OFF なので明示的に ON にする。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SCENARIO,
    GOAL_STATUS_ACTIVE,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)
_SURVIVAL_V2_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "survival_island_v2.json"
)
_PERSISTENT_WORLD_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "persistent_world_demo.json"
)


class TestWorldRuntimeGoalStoreWiring:
    def test_flag_off_keeps_static_objective_and_no_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GOAL_STORE_ENABLED", raising=False)
        runtime = create_world_runtime(_SCENARIO_PATH)
        assert runtime._goal_journal_store is None

    def test_flag_on_builds_store_and_seeds_locked_scenario_goal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("GOAL_STORE_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        assert runtime._goal_journal_store is not None

        scenario_text = runtime._resolve_scenario_llm_objective_text()
        player_id = PlayerId(1)

        # 初回描画: 静的文字列と同一を返しつつ、locked scenario goal を seed する。
        rendered = runtime._resolve_objective_via_goal_store(player_id, scenario_text)
        assert rendered == scenario_text  # ← 挙動不変 (質感テストの本命)

        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, player_id
        )
        entries = runtime._goal_journal_store.list_all_by_being(being_id)
        assert len(entries) == 1
        seeded = entries[0]
        assert seeded.text == scenario_text
        assert seeded.status == GOAL_STATUS_ACTIVE
        assert seeded.locked is True
        assert seeded.origin == GOAL_ORIGIN_SCENARIO

    def test_seed_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """2 回描画しても seed は 1 件だけ (get_active が既存を返す)。"""
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("GOAL_STORE_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        scenario_text = runtime._resolve_scenario_llm_objective_text()
        player_id = PlayerId(1)

        runtime._resolve_objective_via_goal_store(player_id, scenario_text)
        second = runtime._resolve_objective_via_goal_store(player_id, scenario_text)

        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, player_id
        )
        assert second == scenario_text
        assert len(runtime._goal_journal_store.list_all_by_being(being_id)) == 1


class TestWorldRuntimeGoalStoreLongScenarioText:
    """HIGH-1 回帰: 長い目的文 (300字超) のシナリオでも【現在の目的】が消えない。

    survival_island_v2 の llm_objective_text は 309 字で、旧 GoalEntry の
    MAX_GOAL_TEXT_CHARS (200字) を超えていた。GOAL_STORE_ENABLED=1 の run では
    遅延 seed が GoalEntryValidationException を投げ、provider が ERROR ログ +
    空文字へ縮退して【現在の目的】section 自体が消えていた (毎ターン)。
    """

    def test_survival_island_v2_objective_renders_full_text_with_goal_store_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("GOAL_STORE_ENABLED", "1")
        runtime = create_world_runtime(_SURVIVAL_V2_PATH)
        player_id = runtime.get_player_ids()[0]
        scenario_text = runtime._resolve_scenario_llm_objective_text()
        assert len(scenario_text) > 200  # 旧上限を超える実データであることの前提確認

        prompt = runtime.build_full_prompt(player_id)
        user = prompt["messages"][1]["content"]

        # section 自体が省略されず、目的文の全文が描画される (以前は空に縮退)。
        assert "【現在の目的】" in user
        assert "狼煙" in user
        assert "山頂" in user

        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, player_id
        )
        seeded = runtime._goal_journal_store.get_active_by_being(being_id)
        assert seeded is not None
        assert seeded.text == scenario_text
        assert seeded.locked is True


class TestWorldRuntimeGoalLockedByHasGoal:
    """HIGH-3 回帰: seed の locked は _scenario_has_goal (勝敗条件の有無) に連動する。

    以前は全シナリオで locked=True を固定していた。目的文なしの run は作れない
    ため、どんな run でも goal_update / goal_outcome が 100% 拒否され、P6
    (言い直し) / P8 (清算) の実効経路が存在しなかった。
    """

    def test_outcome_resolution_scenario_still_seeds_locked_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """survival_island_v2 は win/lose 配列が空で outcome_resolution が
        勝敗を決める (罠: win/lose だけを見ると誤って unlocked と判定される)。
        outcome_resolution_config の有無を含めて判定することで、locked=True
        (従来どおり goal_update / goal_outcome を拒否) を維持する。
        """
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("GOAL_STORE_ENABLED", "1")
        monkeypatch.setenv("GOAL_REVISION_ENABLED", "1")
        runtime = create_world_runtime(_SURVIVAL_V2_PATH)
        # v2 は win/lose 配列が空 (outcome_resolution 駆動) であることの前提確認。
        assert runtime.scenario.win_conditions == ()
        assert runtime.scenario.lose_conditions == ()
        assert runtime.scenario.outcome_resolution_config is not None

        scenario_text = runtime._resolve_scenario_llm_objective_text()
        player_id = runtime.get_player_ids()[0]
        runtime._resolve_objective_via_goal_store(player_id, scenario_text)

        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, player_id
        )
        seeded = runtime._goal_journal_store.get_active_by_being(being_id)
        assert seeded is not None
        assert seeded.locked is True

        # 従来どおり goal_update は拒否され、目的は書き換わらない。
        runtime.apply_goal_update_if_present(
            player_id, {"goal_update": "宝探しに切り替える"}
        )
        active = runtime._goal_journal_store.get_active_by_being(being_id)
        assert active.goal_id == seeded.goal_id

    def test_open_world_scenario_seeds_locked_false_and_allows_revision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """persistent_world_demo (勝敗条件なし) は locked=False で seed され、
        goal_update (言い直し / P6) と goal_outcome のみでの清算 (無目的に戻り
        「(まだ定まっていない)」描画 / P8) の両方が初めて実効的に通る。
        """
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("GOAL_STORE_ENABLED", "1")
        monkeypatch.setenv("GOAL_REVISION_ENABLED", "1")
        runtime = create_world_runtime(_PERSISTENT_WORLD_PATH)
        assert runtime.scenario.win_conditions == ()
        assert runtime.scenario.lose_conditions == ()
        assert runtime.scenario.outcome_resolution_config is None

        scenario_text = runtime._resolve_scenario_llm_objective_text()
        player_id = runtime.get_player_ids()[0]
        runtime._resolve_objective_via_goal_store(player_id, scenario_text)

        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, player_id
        )
        seeded = runtime._goal_journal_store.get_active_by_being(being_id)
        assert seeded is not None
        assert seeded.locked is False

        # P6: goal_update で言い直せる (以前は locked=True で必ず拒否されていた)。
        runtime.apply_goal_update_if_present(
            player_id, {"goal_update": "灯台を修理する"}
        )
        active = runtime._goal_journal_store.get_active_by_being(being_id)
        assert active.text == "灯台を修理する"
        assert active.supersedes == seeded.goal_id

        # P8: goal_outcome のみで無目的に戻り、未定表示になる。
        runtime.apply_goal_update_if_present(player_id, {"goal_outcome": "achieved"})
        assert runtime._goal_journal_store.get_active_by_being(being_id) is None
        rendered = runtime._resolve_objective_via_goal_store(player_id, "")
        assert "まだ定まっていない" in rendered
