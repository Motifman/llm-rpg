"""世界文脈の条件が、実際の runtime の状態を読んで発火することを保証する。

評価器単体で条件が成立しても、runtime が別の store や graph を渡していれば
scenario event は永久に発火しない。公開入口で状態を動かして配線まで固定する。
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_DRILL = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "station_drill.json"
)


def _scenario_with_probe(tmp_path: Path, condition: dict) -> Path:
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw.setdefault("scenario_events", []).append(
        {
            "id": "world_context_runtime_probe",
            "trigger": "ON_TICK",
            "once": True,
            "conditions": [condition],
            "effects": [
                {
                    "effect_type": "SET_FLAG",
                    "parameters": {
                        "flag_name": "world_context_runtime_probe_fired",
                        "value": True,
                    },
                }
            ],
        }
    )
    path = tmp_path / "world_context_runtime_probe.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _probe_fired(runtime) -> bool:
    return (
        "world_context_runtime_probe_fired"
        in runtime._world_flag_state.as_frozen_set()
    )


class TestGamePhaseConditionRuntimeWiring:
    """`GAME_PHASE_IS` は runtime が遷移させる唯一の phase store を読む。"""

    def test_event_fires_after_the_runtime_enters_a_meeting(self, tmp_path) -> None:
        """自由時間では発火せず、公開入口で会議へ入った次の tick に発火する。"""
        scenario = _scenario_with_probe(
            tmp_path,
            {"condition_type": "GAME_PHASE_IS", "game_phase": "MEETING"},
        )
        runtime = create_world_runtime(scenario)

        runtime.advance_tick()
        assert _probe_fired(runtime) is False

        runtime.begin_meeting(
            initiator_player_id=PlayerId(1),
            trigger="emergency_button",
        )
        runtime.advance_tick()

        assert _probe_fired(runtime) is True


class TestPlayersAtSpotConditionRuntimeWiring:
    """`PLAYERS_AT_SPOT` は runtime が配置した graph の在席数を読む。"""

    def test_event_fires_when_required_players_are_at_the_spot(self, tmp_path) -> None:
        """5人が集会室に居る初期状態では、必要人数5人の出来事が発火する。"""
        scenario = _scenario_with_probe(
            tmp_path,
            {
                "condition_type": "PLAYERS_AT_SPOT",
                "target_spot": "hall",
                "required_player_count": 5,
            },
        )
        runtime = create_world_runtime(scenario)

        runtime.advance_tick()

        assert _probe_fired(runtime) is True

    def test_event_does_not_fire_when_required_players_are_missing(
        self, tmp_path
    ) -> None:
        """5人しか居ない集会室では、必要人数6人の出来事は発火しない。

        発火する側だけでは、条件を常に真にしても公開入口の試験が通る。
        不成立側も同じ入口で固定し、runtime の配線が人数を無視していないことを
        保証する。
        """
        scenario = _scenario_with_probe(
            tmp_path,
            {
                "condition_type": "PLAYERS_AT_SPOT",
                "target_spot": "hall",
                "required_player_count": 6,
            },
        )
        runtime = create_world_runtime(scenario)

        runtime.advance_tick()

        assert _probe_fired(runtime) is False
