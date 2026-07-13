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
