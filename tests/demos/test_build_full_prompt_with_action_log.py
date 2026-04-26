"""EscapeGameRuntime.build_full_prompt_with_action_log のスモーク。"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "abandoned_hospital.json"


def test_build_full_prompt_with_action_log_includes_split_sections() -> None:
    from demos.escape_game.escape_game_runtime import create_escape_game_runtime

    runtime = create_escape_game_runtime(SCENARIO_PATH)
    pid = PlayerId(runtime.scenario.player_spawns[0].player_id)
    full = runtime.build_full_prompt_with_action_log(
        pid,
        (
            {
                "when": "0:00",
                "where": "テスト",
                "what": "spot_graph_travel_to({})",
                "result": "移動した",
            },
        ),
    )
    u = full["user"]
    assert "【直近の出来事：観測】" in u
    assert "【直近の出来事：行動（時刻・場所・行動・結果）】" in u
    assert "時刻: 0:00" in u
    assert "テスト" in u


def test_format_action_log_for_prompt_empty() -> None:
    from demos.escape_game.escape_game_runtime import EscapeGameRuntime

    assert "まだ" in EscapeGameRuntime.format_action_log_for_prompt(())
