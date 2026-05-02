"""EscapeGameRuntime.build_full_prompt のスモーク。"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "abandoned_hospital.json"


def test_build_full_prompt_includes_merged_recent_and_headings() -> None:
    from demos.escape_game.escape_game_runtime import create_escape_game_runtime

    runtime = create_escape_game_runtime(SCENARIO_PATH)
    pid = PlayerId(runtime.scenario.player_spawns[0].player_id)
    full = runtime.build_full_prompt(pid)
    u = full["user"]
    assert "【直近の出来事】" in u
    assert "memory_query" in u
    assert "【仮説・作業メモ（未確定）】" in u
    assert "【確定した事実（長期メモの抜粋）】" in u
    assert "【関連する思い出（エピソード）】" in u
    assert "【次に試せそうなこと" not in u
