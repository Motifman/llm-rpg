"""StagnationPressureRepository — 「停滞感」カウンタの per-Being 保管庫 interface。

P-U2 (goal_utility_gradient_design.md): 目的への停滞を、空腹のような
**感じられる持続状態** として蓄積するための基盤機能。ただしゲーム物理では
「目的までの距離」を測れないため、reflect (``BeliefConsolidationCoordinator``
の P4/P7) が返す verdict (stalled / achieved / misaligned) を数えるだけの
決定論カウンタにする — P-U1 (evidence 化) と同じ検出器を無意識/意識の
両方が共有する設計。

値そのものは目的の内容やゲーム物理量と無関係な、単なる 0 以上の int。
一次キーは ``BeingId`` (経験の連続性を持つ主体単位)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId


class StagnationPressureRepository(ABC):
    """being ごとに停滞感カウンタ (0 以上の int) を保持する。未記録は 0 として扱う。"""

    @abstractmethod
    def get_by_being(self, being_id: BeingId) -> int:
        """現在のカウンタ値を返す。未記録なら 0。"""

    @abstractmethod
    def increment_by_being(self, being_id: BeingId) -> int:
        """カウンタを 1 増やし、増やした後の値を返す (reflect が stalled /
        misaligned と判定した回に呼ぶ)。"""

    @abstractmethod
    def reset_by_being(self, being_id: BeingId) -> None:
        """カウンタを 0 に戻す (reflect が achieved = 目的への前進を認めた回に呼ぶ)。"""

    @abstractmethod
    def replace_all_by_being(self, being_id: BeingId, value: int) -> None:
        """snapshot restore 用の bulk overwrite (checklist #27)。"""


__all__ = ["StagnationPressureRepository"]
