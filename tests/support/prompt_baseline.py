"""比べる資料にするプロンプトを、シナリオから組む。

資料 (``tests/fixtures/prompts/*.json``) は、作業記憶の取り決めの型を入れる前の main
(``21a33e4c9``) でこのモジュールを走らせて書いた。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (
    inject_dynamic_argument_candidate_table,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import ToolCallLoopGuardService
from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime, create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_DIR = REPO_ROOT / "tests" / "fixtures" / "prompts"
BASELINE_SCENARIOS = ("mine_village_v1", "station_drill")
_REPEATED_WAITS = 3


def baseline_path(scenario_name: str) -> Path:
    return BASELINE_DIR / f"{scenario_name}.json"


def build_baseline(scenario_name: str) -> dict[str, Any]:
    """最初のターンの全員と、1 人目が同じ待機を繰り返した直後のターンを組む。

    繰り返した直後のターンには、繰り返しの警告と、短期記憶に積まれた警告の出来事が出る。
    """
    return {
        "first_turn": _first_turn(scenario_name),
        "after_repeated_waits": _after_repeated_waits(scenario_name),
    }


def _first_turn(scenario_name: str) -> dict[str, dict[str, str]]:
    runtime = _runtime(scenario_name)
    return {str(pid.value): _prompt(runtime, pid) for pid in runtime.get_player_ids()}


def _after_repeated_waits(scenario_name: str) -> dict[str, str]:
    runtime = _runtime(scenario_name)
    guard = ToolCallLoopGuardService(
        observation_buffer=runtime._obs_buffer,
        time_label_provider=lambda: None,
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    runtime.set_tool_call_loop_guard(guard)
    player_id = runtime.get_player_ids()[0]
    for _ in range(_REPEATED_WAITS):
        guard.record_and_check(player_id, "wait", {}, success=True, result_summary="しばらく待った。")
    return _prompt(runtime, player_id)


def _runtime(scenario_name: str) -> WorldRuntime:
    return create_world_runtime(REPO_ROOT / "data" / "scenarios" / f"{scenario_name}.json")


def _prompt(runtime: WorldRuntime, player_id: PlayerId) -> dict[str, str]:
    tool_names = {d.name for d in runtime.get_tool_definitions(player_id=player_id)}
    prompt = inject_dynamic_argument_candidate_table(runtime.build_full_prompt(player_id), tool_names)
    system, user = (m["content"] for m in prompt["messages"])
    return {"system": system, "user": user}


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    for name in BASELINE_SCENARIOS:
        text = json.dumps(build_baseline(name), ensure_ascii=False, indent=2) + "\n"
        baseline_path(name).write_text(text, encoding="utf-8")
