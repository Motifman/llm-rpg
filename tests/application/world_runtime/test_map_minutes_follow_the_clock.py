"""地図に出る移動時間が、世界の時計と同じ換算で書かれる (#1567)。

`_minutes_per_tick` が `day_night_config.ticks_per_day` を `getattr` で読んで
いた。値は `day_night_config.cycle.ticks_per_day` にあり、既定値の 5 分/tick に
黙って倒れていた。廃坑の山村 (1 tick = 30 分) では、地図が 6 分の 1 の時間を
書き、エージェントは間に合わない往復を計画した。
"""

from __future__ import annotations

import re
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import (
    _minutes_per_tick,
    create_world_runtime,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
#: 昼夜を宣言し、1 日 48 tick (= 30 分/tick) の世界。
_MINE = _SCENARIOS / "mine_village_v1.json"
#: 昼夜を宣言しない世界。
_DRILL = _SCENARIOS / "station_drill.json"


def _clock_minutes(label: str) -> int:
    match = re.search(r"Day (\d+) (?:深夜 )?(\d+):(\d+)", label)
    assert match is not None, label
    day, hour, minute = (int(g) for g in match.groups())
    return (day - 1) * 24 * 60 + hour * 60 + minute


class TestMinutesPerTick:
    """1 tick の分数を、シナリオの昼夜宣言から決める。"""

    def test_day_night_world_derives_minutes_from_cycle_ticks_per_day(self) -> None:
        """昼夜を宣言したシナリオでは、1 tick の分が 24 時間を cycle.ticks_per_day で割った値になる。"""
        scenario = ScenarioLoader().load_from_file(_MINE)
        assert scenario.day_night_config is not None
        ticks_per_day = scenario.day_night_config.cycle.ticks_per_day

        minutes = _minutes_per_tick(scenario)

        assert minutes == (24 * 60) // ticks_per_day

    def test_world_without_day_night_keeps_five_minutes_per_tick(self) -> None:
        """昼夜を宣言しないシナリオは、これまでどおり 5 分/tick になる。"""
        scenario = ScenarioLoader().load_from_file(_DRILL)
        assert scenario.day_night_config is None

        minutes = _minutes_per_tick(scenario)

        assert minutes == 5


class TestMapAgreesWithTheClock:
    """地図の分と、同じ移動で進む時計の分が一致する。"""

    def test_map_travel_minutes_match_clock_advance_over_the_same_ticks(self) -> None:
        """下層の近道から昇降機の乗り場までの地図の分が、その tick 数だけ時計を進めた差と一致する。"""
        runtime = create_world_runtime(_MINE)
        names = {str(s.spot_id): s.name for s in runtime.scenario.graph.iter_spot_nodes()}
        origin, destination = "下層の近道", "昇降機の乗り場"
        travel_ticks = next(
            c.travel_ticks
            for c in runtime.scenario.graph.all_connections()
            if names[str(c.from_spot_id)] == origin
            and names[str(c.to_spot_id)] == destination
        )
        prompt = (
            runtime._world_llm_system_prompts_by_player_id.get(1)
            or runtime._world_llm_system_prompt
        )
        origin_line = next(
            line for line in prompt.splitlines() if line.startswith(f"  {origin} ")
        )
        before = _clock_minutes(runtime._time_label())

        for _ in range(travel_ticks):
            runtime.advance_tick()
        clock_elapsed = _clock_minutes(runtime._time_label()) - before

        assert f"{destination} まで {clock_elapsed} 分" in origin_line
