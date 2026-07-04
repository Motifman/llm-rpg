"""N2: interact tool の precondition 失敗 surface 強化。

実験 #25 で確認された N2 問題: 採取枯渇後の retry が generic な
"LLM ツール実行に失敗しました" に潰されていて、LLM が同じ枯渇
resource に何度も retry を続けていた。

このテストは:
- `InteractionNotAllowedException` の reason がそのまま LLM 向け
  message に乗ること
- 枯渇系の reason に対して「同じ object に retry しない」旨の
  remediation が選ばれること
- 通常の precondition 不足では別の remediation が出ること
を保証する。
"""

from __future__ import annotations

# PR-θ3 (経路統合): _interact_remediation_for_reason は
# application/llm/services/executors/interact_helpers.py に移動した。
from ai_rpg_world.application.llm.services.executors.interact_helpers import (
    interact_remediation_for_reason as _interact_remediation_for_reason,
)


class TestInteractRemediationKeywords:
    """`_interact_remediation_for_reason` のキーワード分岐。"""

    def test_採り尽くした_reason_は_retry_抑制_remediation(self) -> None:
        """「近くの蔓は採り尽くした」のような reason で枯渇 remediation。"""
        rem = _interact_remediation_for_reason("近くの蔓は採り尽くした。")
        assert "同じ object に同 action_name を再試行しても結果は変わらない" in rem

    def test_枯渇_reason_でも_retry_抑制_remediation(self) -> None:
        """「枯渇」を含む reason でも同 remediation。"""
        rem = _interact_remediation_for_reason("資源が枯渇している")
        assert "別の場所・別 object・別 action" in rem

    def test_もう開いている_reason_でも_retry_抑制(self) -> None:
        """すでに完了している interaction (chest opened 等) も retry 抑制。"""
        rem = _interact_remediation_for_reason("宝箱はもう空だ。")
        assert "再試行しても結果は変わらない" in rem

    def test_燃え上がっている_reason_でも_retry_抑制(self) -> None:
        """狼煙台 lit=True 再点火など、対象状態が既達なら retry 不要。"""
        rem = _interact_remediation_for_reason("狼煙はすでに燃え上がっている。")
        assert "再試行しても結果は変わらない" in rem

    def test_アイテム不足_reason_では_前提条件_remediation(self) -> None:
        """「流木が足りない」のような precondition 不足は通常 remediation。"""
        rem = _interact_remediation_for_reason("流木が足りない。")
        assert "前提条件" in rem
        assert "再試行しても結果は変わらない" not in rem

    def test_火打ち石_必要_reason_でも_前提条件_remediation(self) -> None:
        """「火打ち石が必要だ」もアイテム不足扱い (= 揃えれば成功)。"""
        rem = _interact_remediation_for_reason("火打ち石が必要だ。")
        assert "前提条件" in rem
        assert "再試行しても結果は変わらない" not in rem
