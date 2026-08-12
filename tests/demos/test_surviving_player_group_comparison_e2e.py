"""生存人数の比較条件へ runtime が役割と終局結果を配線することを保証する。"""

from __future__ import annotations

import json
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum


_STATION_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_CREW = tuple(PlayerId(value) for value in (1, 2, 4, 5))


def _scenario_with_comparison_condition(tmp_path: Path) -> Path:
    scenario = json.loads(_STATION_DRILL.read_text(encoding="utf-8"))
    scenario["game_end_conditions"]["lose"] = [
        {
            "type": "SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE",
            "required_state": {"role": "crew"},
            "comparison_state": {"role": "keeper"},
        }
    ]
    path = tmp_path / "station_drill_comparison.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    return path


def test_runtime_supplies_both_groups_and_their_outcomes(tmp_path: Path) -> None:
    """runtime 上でも crew 1 人、keeper 1 人になった境界で敗北する。

    評価器の単体試験だけでは、runtime が新しい条件へ player_states と
    player_outcomes を渡し忘れても検出できない。実シナリオから読み、追放を
    経由して本番の ``check_game_end`` を通す。
    """
    runtime = create_world_runtime(_scenario_with_comparison_condition(tmp_path))

    for player_id in _CREW[:2]:
        runtime.eject_player(player_id)
    assert runtime.check_game_end().is_ended is False

    runtime.eject_player(_CREW[2])
    result = runtime.check_game_end()

    assert result.is_ended is True
    assert result.result is GameResultEnum.LOSE
