"""Issue #171a: ``WorldRuntime`` がシナリオの TICK_LIMIT lose_condition
から残り tick を計算し、``PlayerCurrentStateDto.tick_budget_remaining`` 経由
で LLM プロンプトに配線するかを検証する。

責務:
- コードはメタ情報「時間切れまで」の残り時間しか流さない (WIN 条件はシナリオ責務)
- TICK_LIMIT が無いシナリオでは None のまま (セクションごと出さない)
"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.application.being.world_state_snapshot_service import WorldStateSnapshotService
from ai_rpg_world.application.being.world_subsystems.world_tick_codec import WorldTickSubsystemCodec
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "forbidden_library_demo.json"


class TestTickBudgetWiring:
    """forbidden_library_demo は TICK_LIMIT=80 を持つので残量が計算される。"""

    def test_initial_budget_equals_scenario_limit(self) -> None:
        """tick=0 の初期状態では残量 = scenario の tick_limit。"""
        rt = create_world_runtime(_SCENARIO_PATH)
        assert rt._compute_tick_budget_remaining() == 80

    def test_budget_decreases_as_tick_advances(self) -> None:
        """内部 tick を進めると残量が減る。"""
        rt = create_world_runtime(_SCENARIO_PATH)
        rt._time_provider.advance_tick(10)
        assert rt._compute_tick_budget_remaining() == 70

    def test_budget_clamped_to_zero_when_exceeded(self) -> None:
        """tick が limit を超えても負にはならない (0 にクランプ)。"""
        rt = create_world_runtime(_SCENARIO_PATH)
        rt._time_provider.advance_tick(99)
        assert rt._compute_tick_budget_remaining() == 0

    def test_budget_uses_world_tick_restored_from_snapshot(self) -> None:
        """snapshot から復元した world tick が残り時間に反映される。"""
        source = create_world_runtime(_SCENARIO_PATH)
        source._time_provider.set_current_tick(25)
        snapshot_service = WorldStateSnapshotService(subsystem_codecs=[WorldTickSubsystemCodec()])
        snapshot = snapshot_service.capture(
            source,
            source_scenario="forbidden_library_demo",
            world_tick=source.current_tick(),
        )

        restored = create_world_runtime(_SCENARIO_PATH)
        snapshot_service.restore(restored, snapshot, current_scenario="forbidden_library_demo")

        assert restored.current_tick() == 25
        assert restored._compute_tick_budget_remaining() == 55
        player_id = restored.get_player_ids()[0]
        assert "時間切れまで: あと 275 分" in restored.build_observation(player_id)

    def test_prompt_contains_remaining_tick_line(self) -> None:
        """build_observation のテキストに残量行が含まれる (フォーマッタ経由)。"""
        rt = create_world_runtime(_SCENARIO_PATH)
        # プレイヤー 0 を取得 (シナリオに必ず居る前提)
        player_ids = rt.get_player_ids()
        assert player_ids, "シナリオに player_spawn が無い"
        text = rt.build_observation(player_ids[0])
        assert "時間切れまで: あと 400 分" in text
        assert "残り行動可能 tick" not in text
