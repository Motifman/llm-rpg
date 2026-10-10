"""初期配置で同じ場所にいた相手を、Being が最初から会った相手として持つことを保証する。"""

from __future__ import annotations

from pathlib import Path

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"


class TestAcquaintancesAtSpawn:
    """create_world_runtime が、初期配置の同席を知り合いの記録に残すことを保証する。"""

    def test_players_spawned_together_have_met_each_other_at_turn_zero(self) -> None:
        """島 (4 人が同じ浜から始まる) では、各自が他の 3 人とターン 0 に 1 回会ったことになっていて、自分は含まない。"""
        runtime = create_world_runtime(_SCENARIOS / "survival_island_v4_coop.json")
        names = {pid: runtime.get_player_name(pid) for pid in runtime.get_player_ids()}

        for pid, own_name in names.items():
            others = sorted(n for n in names.values() if n != own_name)
            met = [runtime._player_acquaintances.find(pid, n) for n in others]
            assert all(m is not None for m in met), (own_name, met)
            assert {(m.first_met_turn, m.met_count) for m in met} == {(0, 1)}
            assert runtime._player_acquaintances.find(pid, own_name) is None

    def test_players_spawned_apart_have_not_met(self) -> None:
        """別々の場所から始まる禁書庫では、起動直後に誰とも会っていない。"""
        runtime = create_world_runtime(_SCENARIOS / "forbidden_library_demo.json")
        kaito, rin = runtime.get_player_ids()[:2]

        assert runtime._player_acquaintances.find(kaito, "リン") is None
        assert runtime._player_acquaintances.find(rin, "カイト") is None
