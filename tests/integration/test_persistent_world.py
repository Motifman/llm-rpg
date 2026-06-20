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
    from ai_rpg_world.application.world_runtime.world_runtime import (
        create_world_runtime,
    )

    return create_world_runtime(
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
        永続世界にも勝敗が漏れる。config が勝敗を一切持たないことを固定する。

        マッチは underscore で区切られた token 単位で行う (= 単純な部分一致だと
        ``window`` が ``win`` に hit する等の偽陽性を起こすため)。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests()
        field_names = set(vars(cfg).keys())
        for forbidden in ("win", "lose", "victory", "defeat", "game_end"):
            for name in field_names:
                tokens = set(name.split("_"))
                # game_end は 2 語複合のため、name に "game" と "end" が両方含まれるかも見る
                if forbidden == "game_end":
                    assert not (
                        "game" in tokens and "end" in tokens
                    ), f"config が勝敗概念 ({forbidden}) を持っている: {name}"
                else:
                    assert forbidden not in tokens, (
                        f"config が勝敗概念 ({forbidden}) を持っている: {name}"
                    )


class TestPersistentWorldSystemPromptIsNeutral:
    """層2: 永続世界の system prompt に escape/goal 前提が漏れない。"""

    def _system_prompt(self, runtime) -> str:
        player_id = runtime.get_player_ids()[0]
        prompt = runtime.build_full_prompt(player_id)
        return "\n".join(
            m.get("content", "")
            for m in prompt.get("messages", [])
            if m.get("role") == "system"
        )

    def test_no_escape_or_goal_framing_in_persistent_world(self) -> None:
        """勝敗のない永続世界では「脱出できない」「勝利条件 (最終目的)」が出ない。"""
        system = self._system_prompt(_create_runtime())
        assert "脱出できない" not in system
        assert "勝利条件 (最終目的)" not in system
        assert "全て最終目的のための手段である" not in system
        # 中立文が入る
        assert "固定された勝敗や達成すべき最終目的はない" in system
