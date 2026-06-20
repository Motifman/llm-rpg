"""永続世界 (勝敗のない世界) の終了条件契約 (U5)。

勝敗をフラグ化した結果、``win_conditions`` / ``lose_conditions`` を宣言しない
シナリオは「終了条件のない永続世界」になる。``check_game_end`` は決して
``is_ended=True`` を返さず、driver は外的停止 (MAX_WORLD_TICKS) でしか止まらない。

この回帰テストは「勝敗条件を書かなければ永続世界になる」という capability を
固定し、将来 escape 固有の勝敗概念を runtime に再注入してしまう変更を検出する。
作り方は docs/design_decisions.md に記載。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)

# 勝敗条件 (win_conditions / lose_conditions) も outcome_resolution も宣言しない
# 永続世界の参照シナリオ (U5 で追加)。
_PERSISTENT_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "persistent_world_demo.json"
)


def _create_runtime():
    from ai_rpg_world.application.escape_game.escape_game_runtime import (
        create_escape_game_runtime,
    )

    return create_escape_game_runtime(
        _PERSISTENT_SCENARIO, config=ResolvedLlmRuntimeConfig.for_tests()
    )


class TestPersistentWorldHasNoEndCondition:
    """勝敗条件ゼロのシナリオは永続世界 (check_game_end が終了を返さない)。"""

    def test_scenario_declares_no_win_lose_or_outcome(self) -> None:
        """このシナリオは win/lose/outcome を一切宣言しない (= 永続世界の前提)。"""
        runtime = _create_runtime()
        assert runtime.scenario.win_conditions == ()
        assert runtime.scenario.lose_conditions == ()
        assert runtime.scenario.outcome_resolution_config is None

    def test_check_game_end_never_ends_at_start(self) -> None:
        """開始直後、check_game_end は is_ended=False (「ゲーム続行中」)。"""
        runtime = _create_runtime()
        result = runtime.check_game_end()
        assert result.is_ended is False
        assert result.result is None

    def test_check_game_end_stays_not_ended_after_ticks(self) -> None:
        """tick を進めても永続世界は自発終了しない (外的停止のみで止まる)。"""
        runtime = _create_runtime()
        for _ in range(5):
            runtime.advance_tick()
        assert runtime.check_game_end().is_ended is False

    def test_config_does_not_inject_win_loss(self) -> None:
        """ResolvedLlmRuntimeConfig は勝敗概念を持たない (勝敗はシナリオ専管)。

        runtime 設定 (config) 側に win/lose を足してしまうと、シナリオで宣言しない
        永続世界にも勝敗が漏れる。config が勝敗を一切持たないことを固定する。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests()
        field_names = set(vars(cfg).keys())
        for forbidden in ("win", "lose", "victory", "defeat", "game_end"):
            assert not any(forbidden in name for name in field_names), (
                f"config が勝敗概念 ({forbidden}) を持っている: {field_names}"
            )
