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
from tests.runtime_config_helpers import episodic_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _goal_config(*, revision: bool, **overrides):
    values = {
        "goal_store_enabled": True,
        "goal_revision_enabled": revision,
    }
    values.update(overrides)
    return episodic_config(**values)


def _field_in_defs(runtime, field: str) -> bool:
    for d in runtime.get_tool_definitions():
        if field in (d.parameters.get("properties") or {}):
            return True
    return False


def _goal_update_in_defs(runtime) -> bool:
    return _field_in_defs(runtime, "goal_update")


def _seed_active_self_goal(runtime, player_id, goal_id, text):
    being_id = runtime.aux_being_resolver.resolve_being_id(
        runtime.aux_being_default_world_id, player_id
    )
    runtime._goal_journal_store.add_by_being(
        being_id,
        GoalEntry(
            goal_id=goal_id, player_id=int(player_id.value), text=text,
            status=GOAL_STATUS_ACTIVE, locked=False, origin=GOAL_ORIGIN_SELF,
            created_tick=0, created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        ),
    )
    return being_id


class TestGoalRevisionSchemaWiring:
    def test_tool_schema_is_byte_invariant_across_ticks_when_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """設計判断 #1: flag ON でも tool 定義は tick 間で byte 不変。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=_goal_config(revision=True))
        first = runtime.get_tool_definitions()
        second = runtime.get_tool_definitions()
        # ToolDefinitionDto は dataclass。2 回の呼び出しで完全一致。
        assert first == second
        # goal_update が world-action tool に露出している。
        assert _goal_update_in_defs(runtime)

    def test_goal_update_absent_when_revision_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(_SCENARIO_PATH, config=_goal_config(revision=False))
        assert runtime._goal_revision_applier is None
        assert not _goal_update_in_defs(runtime)

    def test_revision_on_but_store_off_does_not_expose_goal_update(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """config ミス (REVISION ON / STORE OFF) でも goal_update を schema に

        露出しない = 「誘うのに黙って捨てる」静かな失敗を作らない。revision は
        store を前提に実効 OFF へ畳まれる。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=episodic_config(goal_revision_enabled=True),
        )
        assert runtime._goal_journal_store is None
        assert runtime._goal_revision_enabled is False
        assert runtime._goal_revision_applier is None
        # schema に goal_update が出ない (applier が無いのに誘わない)。
        assert not _goal_update_in_defs(runtime)


class TestGoalRevisionWrite:
    def test_apply_supersedes_unlocked_active_goal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(_SCENARIO_PATH, config=_goal_config(revision=True))
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
        runtime = create_world_runtime(_SCENARIO_PATH, config=_goal_config(revision=True))
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
        runtime = create_world_runtime(_SCENARIO_PATH, config=_goal_config(revision=True))
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


class TestGoalOutcomeWiring:
    """P8: goal_outcome の schema 露出と清算・転記の end-to-end 配線。"""

    def test_goal_outcome_exposed_on_and_byte_invariant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """flag ON で goal_outcome が露出し、tool 定義は tick 間 byte 不変 (設計判断 #1)。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=_goal_config(revision=True))
        assert _field_in_defs(runtime, "goal_outcome")
        assert runtime.get_tool_definitions() == runtime.get_tool_definitions()

    def test_goal_outcome_absent_when_revision_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(_SCENARIO_PATH, config=_goal_config(revision=False))
        assert not _field_in_defs(runtime, "goal_outcome")

    def test_achieved_settles_goal_and_transcribes_evidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """goal_outcome=achieved → 目的が ACHIEVED で閉じ、支持 evidence が積まれる。

        applier → 実 transcriber → evidence buffer の end-to-end 配線を通す
        (遅延 holder が正しく埋まっているかの防波堤)。
        """
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_goal_config(
                revision=True,
                belief_evidence_enabled=True,
                semantic_search_enabled=True,
            ),
        )
        player_id = PlayerId(1)
        being_id = _seed_active_self_goal(runtime, player_id, "g1", "古い地図を手に入れる")

        runtime.apply_goal_update_if_present(player_id, {"goal_outcome": "achieved"})

        # 目的は ACHIEVED で閉じ、active が無くなる (無目的)。
        assert runtime._goal_journal_store.get_active_by_being(being_id) is None
        entries = {
            e.goal_id: e
            for e in runtime._goal_journal_store.list_all_by_being(being_id)
        }
        assert entries["g1"].status == "achieved"
        # 支持 evidence が buffer に積まれている (実 transcriber 経由)。
        transcriber = runtime._goal_revision_applier._settlement_transcriber_provider()
        assert transcriber is not None
        rows = transcriber._buffer_store.list_all_by_being(being_id)
        assert any("成し遂げた" in r.text for r in rows)

    def test_outcome_only_returns_to_no_goal_render(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """goal_outcome のみで閉じた後、【現在の目的】が未定描画に戻る。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=_goal_config(revision=True))
        player_id = PlayerId(1)
        _seed_active_self_goal(runtime, player_id, "g1", "山頂で狼煙を上げる")

        runtime.apply_goal_update_if_present(player_id, {"goal_outcome": "abandoned"})

        # fallback を空にして seed を誘発させず、無目的の描画を確認する。
        rendered = runtime._resolve_objective_via_goal_store(player_id, "")
        assert "まだ定まっていない" in rendered
