"""P4 (reflect): world_runtime を通した goal reflect の配線を固定する。

GOAL_REFLECT_ENABLED ON のとき、固着 coordinator に reflect が有効化され、
監査対象の目的 provider と内省観測 sink が届いていること (配線漏れ silent
failure の防波堤)。LLM は呼ばない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
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
