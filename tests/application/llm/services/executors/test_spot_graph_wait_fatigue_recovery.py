"""``spot_graph_wait`` の疲労回復量を保証する (PR-D → 本 PR で追加 buff)。

Y_after_issue621 → PR-D (#629) で wait recovery を 4 → 10 に上げた。
Y_after_pr634 で再走したところ、行動数は +55% に伸びたが、後半に wait の
3 連発 (loop_guard 6 件中 4 件が wait) が観測された。

原因は「自然増加 +1/tick + 行動増加」の合算で wait 1 回 (-10) では 1 ターンの
行動コストすら吸収できないこと。本 PR で:

1. ``DEFAULT_NEED_RATES[FATIGUE] = 1 → 0`` (= 行動以外で増えない)
2. wait recovery 10 → 20 (= 重い行動 attack +5 の 4 回分を一度に回収)

の 2 点をセットで導入し、「待機したい欲求は増えるかもしれないが、連続待機の
回数は減る」状態を作る。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)


class TestFatigueRecoveryWaitValue:
    def test_wait_20(self) -> None:
        """重い行動 ``attack`` (+5) の 4 回分を一度に賄える強度。
        ``DEFAULT_NEED_RATES[FATIGUE] = 0`` と組み合わせて連続待機を不要にする。"""
        assert SpotGraphToolExecutor.FATIGUE_RECOVERY_WAIT == 20

    def test_value_four_regression_check(self) -> None:
        """PR-D で 4 → 10、本 PR で 10 → 20 に上げた。回帰で弱い値に
        戻ってしまうと Y_after_issue621 / Y_after_pr634 の「wait spam」体験
        に逆戻りするので明示的に弾く。"""
        assert SpotGraphToolExecutor.FATIGUE_RECOVERY_WAIT > 10
