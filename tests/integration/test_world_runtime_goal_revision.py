"""P6 (目的の見直し / G2): world_runtime を通した goal_update の配線を固定する。

最重要: GOAL_REVISION_ENABLED ON の run で tool 定義が tick 間 byte 不変である
こと (設計判断 #1 = prefix cache を守る)。加えて goal_update の露出・書き込み
(supersede)・flag OFF での不在を確認する。LLM は呼ばない。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_SUPERSEDED,
    GoalEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _enable(monkeypatch, revision: bool) -> None:
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("GOAL_STORE_ENABLED", "1")
    if revision:
        monkeypatch.setenv("GOAL_REVISION_ENABLED", "1")
    else:
        monkeypatch.delenv("GOAL_REVISION_ENABLED", raising=False)


def _goal_update_in_defs(runtime) -> bool:
    for d in runtime.get_tool_definitions():
        if "goal_update" in (d.parameters.get("properties") or {}):
            return True
    return False


class TestGoalRevisionSchemaWiring:
    def test_tool_schema_is_byte_invariant_across_ticks_when_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """設計判断 #1: flag ON でも tool 定義は tick 間で byte 不変。"""
        _enable(monkeypatch, revision=True)
        runtime = create_world_runtime(_SCENARIO_PATH)
        first = runtime.get_tool_definitions()
        second = runtime.get_tool_definitions()
        # ToolDefinitionDto は dataclass。2 回の呼び出しで完全一致。
        assert first == second
        # goal_update が world-action tool に露出している。
        assert _goal_update_in_defs(runtime)

    def test_goal_update_absent_when_revision_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable(monkeypatch, revision=False)
        runtime = create_world_runtime(_SCENARIO_PATH)
        assert runtime._goal_revision_applier is None
        assert not _goal_update_in_defs(runtime)

    def test_revision_on_but_store_off_does_not_expose_goal_update(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """config ミス (REVISION ON / STORE OFF) でも goal_update を schema に

        露出しない = 「誘うのに黙って捨てる」静かな失敗を作らない。revision は
        store を前提に実効 OFF へ畳まれる。"""
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.delenv("GOAL_STORE_ENABLED", raising=False)
        monkeypatch.setenv("GOAL_REVISION_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        assert runtime._goal_journal_store is None
        assert runtime._goal_revision_enabled is False
        assert runtime._goal_revision_applier is None
        # schema に goal_update が出ない (applier が無いのに誘わない)。
        assert not _goal_update_in_defs(runtime)


class TestGoalRevisionWrite:
    def test_apply_supersedes_unlocked_active_goal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable(monkeypatch, revision=True)
        runtime = create_world_runtime(_SCENARIO_PATH)
        player_id = PlayerId(1)
        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, player_id
        )
        # unlocked な active 目的を用意 (open-world で自分が立てた想定)。
        runtime._goal_journal_store.add_by_being(
            being_id,
            GoalEntry(
                goal_id="g-self", player_id=1, text="魚を分けてもらう",
                status=GOAL_STATUS_ACTIVE, locked=False, origin=GOAL_ORIGIN_SELF,
                created_tick=0, created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            ),
        )

        runtime.apply_goal_update_if_present(
            player_id, {"goal_update": "自力で食料源を確保する"}
        )

        active = runtime._goal_journal_store.get_active_by_being(being_id)
        assert active.text == "自力で食料源を確保する"
        assert active.supersedes == "g-self"
        entries = {e.goal_id: e for e in runtime._goal_journal_store.list_all_by_being(being_id)}
        assert entries["g-self"].status == GOAL_STATUS_SUPERSEDED

    def test_apply_noop_when_goal_update_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable(monkeypatch, revision=True)
        runtime = create_world_runtime(_SCENARIO_PATH)
        player_id = PlayerId(1)
        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, player_id
        )
        before = list(runtime._goal_journal_store.list_all_by_being(being_id))
        runtime.apply_goal_update_if_present(player_id, {"inner_thought": "考え中"})
        after = list(runtime._goal_journal_store.list_all_by_being(being_id))
        assert before == after

    def test_locked_goal_update_rejected_and_emits_observation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """locked 目的への書き換えは拒否され、拒否観測の生成が例外なく通る。

        拒否観測は ``_emit_goal_observation`` 経由で ObservationOutput を組む。
        observation_category が不正だと構築時に落ちるため、この経路を実際に
        通して回帰を防ぐ (fake sink では捉えられない実配線のバグ)。
        """
        _enable(monkeypatch, revision=True)
        runtime = create_world_runtime(_SCENARIO_PATH)
        player_id = PlayerId(1)
        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, player_id
        )
        runtime._goal_journal_store.add_by_being(
            being_id,
            GoalEntry(
                goal_id="g-locked", player_id=1, text="禁書を封印する",
                status=GOAL_STATUS_ACTIVE, locked=True, origin=GOAL_ORIGIN_SELF,
                created_tick=0, created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            ),
        )

        # 拒否観測の生成を含め、例外なく通ること (category バグの回帰ガード)。
        runtime.apply_goal_update_if_present(player_id, {"goal_update": "宝探しに切り替える"})

        active = runtime._goal_journal_store.get_active_by_being(being_id)
        assert active.goal_id == "g-locked"  # locked は書き換わらない
        assert active.text == "禁書を封印する"
