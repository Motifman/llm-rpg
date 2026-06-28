"""``spot_graph_wait`` の疲労回復量を保証する (PR-D / Y_after_issue621 後続)。

Y_after_issue621 trace では wait による疲労回復が体感できず、復帰機構として
機能していなかった。実測:
- 23 wait 前後の fatigue 平均 Δ = +0.9 (= 効いていない、むしろ増)
- P3 は wait 6 回でも fatigue 100 のままロック
- P2 inner_thought (t122): 「**空腹も疲労も100のままだ**」

原因は balance: 1 wait の純減が ``-4 + (+1 passive decay) = -3`` で、他 action
の +1〜5 と相殺すると 100 から脱出できない。本 PR で wait recovery を 10 に
引き上げ、純減 -9/tick で 100 → 70 を 4 連 wait で達成できる強度にする。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)


class TestFatigueRecoveryWaitValue:
    def test_wait_の_疲労回復量は_10(self) -> None:
        """passive decay +1/tick との差分で純減 -9/tick になり、4 連 wait で
        ``exhausted`` (100) から ``severe`` (84) 域に戻れる強度。"""
        assert SpotGraphToolExecutor.FATIGUE_RECOVERY_WAIT == 10

    def test_過去の弱い値_4_に_戻っていない_regression_check(self) -> None:
        """PR-D で 4 → 10 に上げた。回帰で 4 に戻ってしまうと Y_after_issue621
        の「疲労が解消されない」体験に逆戻りするので明示的に弾く。"""
        assert SpotGraphToolExecutor.FATIGUE_RECOVERY_WAIT > 4
