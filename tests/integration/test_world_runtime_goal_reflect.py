"""P4/P7 (reflect): world_runtime を通した goal reflect の配線を固定する。

GOAL_REFLECT_ENABLED ON のとき、固着 coordinator に reflect が有効化され、
監査対象の目的 provider と内省観測 sink が届いていること (配線漏れ silent
failure の防波堤)。P7: 監査対象が goal store の active 目的になること、および
reflect の観測経路が goal store を書き換えない不変条件も固定する。LLM は
呼ばない。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ACTIVE,
    GoalEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _coordinator(runtime):
    stack = runtime._episodic_stack
    assert stack is not None
    return stack.belief_consolidation_coordinator


def _enable_consolidation(monkeypatch) -> None:
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("SEMANTIC_SEARCH_ENABLED", "1")
    monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")


class TestGoalReflectWiring:
    def test_reflect_wired_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable_consolidation(monkeypatch)
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        coord = _coordinator(runtime)
        assert coord is not None
        assert coord._goal_reflect_enabled is True
        assert coord._objective_text_provider is not None
        assert coord._reflect_observation_sink is not None
        # 目的 provider が現在の目的 (シナリオ目的) を返す。
        assert coord._objective_text_provider(PlayerId(1))

    def test_reflect_off_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _enable_consolidation(monkeypatch)
        monkeypatch.delenv("GOAL_REFLECT_ENABLED", raising=False)
        runtime = create_world_runtime(_SCENARIO_PATH)
        coord = _coordinator(runtime)
        assert coord is not None
        assert coord._goal_reflect_enabled is False


class TestGoalStagnationEvidenceWiring:
    """P-U1: GOAL_STAGNATION_EVIDENCE_ENABLED が world_runtime から
    coordinator まで配線され、既定 OFF であることを固定する。"""

    def test_goal_stagnation_evidence_wired_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_consolidation(monkeypatch)
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        monkeypatch.setenv("GOAL_STAGNATION_EVIDENCE_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        coord = _coordinator(runtime)
        assert coord is not None
        assert coord._goal_stagnation_evidence_enabled is True

    def test_goal_stagnation_evidence_off_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_consolidation(monkeypatch)
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        monkeypatch.delenv("GOAL_STAGNATION_EVIDENCE_ENABLED", raising=False)
        runtime = create_world_runtime(_SCENARIO_PATH)
        coord = _coordinator(runtime)
        assert coord is not None
        assert coord._goal_stagnation_evidence_enabled is False


class TestStagnationPressureWiring:
    """P-U2: STAGNATION_PRESSURE_ENABLED が world_runtime から coordinator まで
    配線され、既定 OFF であることを固定する。"""

    def test_stagnation_pressure_wired_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_consolidation(monkeypatch)
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        monkeypatch.setenv("STAGNATION_PRESSURE_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        coord = _coordinator(runtime)
        assert coord is not None
        assert coord._stagnation_pressure_enabled is True
        assert coord._stagnation_pressure_store is not None
        # runtime 側にも store が保持され、snapshot stub から拾える (checklist #27)。
        assert runtime._stagnation_pressure_store is not None
        assert runtime._stagnation_pressure_store is coord._stagnation_pressure_store

    def test_stagnation_pressure_off_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_consolidation(monkeypatch)
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        monkeypatch.delenv("STAGNATION_PRESSURE_ENABLED", raising=False)
        runtime = create_world_runtime(_SCENARIO_PATH)
        coord = _coordinator(runtime)
        assert coord is not None
        assert coord._stagnation_pressure_enabled is False
        assert runtime._stagnation_pressure_store is None


class TestGoalReflectAuditTarget:
    """P7: 監査対象が goal store の active 目的で、reflect が goal store を書かない。"""

    def _seed_active_goal(self, runtime, text: str):
        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, PlayerId(1)
        )
        runtime._goal_journal_store.add_by_being(
            being_id,
            GoalEntry(
                goal_id="g-self", player_id=1, text=text,
                status=GOAL_STATUS_ACTIVE, locked=False, origin=GOAL_ORIGIN_SELF,
                created_tick=0, created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            ),
        )
        return being_id

    def test_audit_target_is_goal_store_active_goal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P7: goal store に自己目的 (active) があれば、それが監査対象になる。"""
        _enable_consolidation(monkeypatch)
        monkeypatch.setenv("GOAL_STORE_ENABLED", "1")
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        self._seed_active_goal(runtime, "自力で食料源を確保する")
        target = _coordinator(runtime)._objective_text_provider(PlayerId(1))
        assert target == "自力で食料源を確保する"

    def test_reflect_observation_does_not_mutate_goal_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P7 不変条件: 達成の内省観測を注入しても goal store は書き換わらない。

        達成の気づきは意識に上げるだけ。status 変更は本人 (P6) が決める ——
        reflect の観測経路が goal を achieved にしてしまわないことを固定する。
        """
        _enable_consolidation(monkeypatch)
        monkeypatch.setenv("GOAL_STORE_ENABLED", "1")
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        being_id = self._seed_active_goal(runtime, "古い地図を手に入れる")
        before = runtime._goal_journal_store.get_active_by_being(being_id)

        runtime._emit_reflect_observation(
            PlayerId(1), "気づけば、地図はもう手に入れている", "achieved"
        )

        after = runtime._goal_journal_store.get_active_by_being(being_id)
        assert after is not None
        assert after.goal_id == before.goal_id
        assert after.status == GOAL_STATUS_ACTIVE
        assert after.text == "古い地図を手に入れる"
