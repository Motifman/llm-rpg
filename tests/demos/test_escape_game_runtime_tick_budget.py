"""Issue #171a: ``EscapeGameRuntime`` がシナリオの TICK_LIMIT lose_condition
から残り tick を計算し、``PlayerCurrentStateDto.tick_budget_remaining`` 経由
で LLM プロンプトに配線するかを検証する。

責務:
- コードはメタ情報「残り行動可能 tick」しか流さない (WIN 条件はシナリオ責務)
- TICK_LIMIT が無いシナリオでは None のまま (セクションごと出さない)
"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "relay_puzzle_demo.json"
)


class TestTickBudgetWiring:
    """relay_puzzle_demo は TICK_LIMIT=50 を持つので残量が計算される。"""

    def test_initial_budget_equals_scenario_limit(self) -> None:
        """tick=0 の初期状態では残量 = scenario の tick_limit。"""
        rt = create_escape_game_runtime(_SCENARIO_PATH)
        assert rt._compute_tick_budget_remaining() == 50

    def test_budget_decreases_as_tick_advances(self) -> None:
        """内部 tick を進めると残量が減る。"""
        rt = create_escape_game_runtime(_SCENARIO_PATH)
        rt._tick = 10
        assert rt._compute_tick_budget_remaining() == 40

    def test_budget_clamped_to_zero_when_exceeded(self) -> None:
        """tick が limit を超えても負にはならない (0 にクランプ)。"""
        rt = create_escape_game_runtime(_SCENARIO_PATH)
        rt._tick = 99
        assert rt._compute_tick_budget_remaining() == 0

    def test_prompt_contains_remaining_tick_line(self) -> None:
        """build_observation のテキストに残量行が含まれる (フォーマッタ経由)。"""
        rt = create_escape_game_runtime(_SCENARIO_PATH)
        # プレイヤー 0 を取得 (シナリオに必ず居る前提)
        player_ids = rt.get_player_ids()
        assert player_ids, "シナリオに player_spawn が無い"
        text = rt.build_observation(player_ids[0])
        assert "残り行動可能 tick: 50" in text
