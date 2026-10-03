from __future__ import annotations

from enum import Enum


class ShapeVerdict(str, Enum):
    """予期を作ったターンに問う形の判定。当たったかではなく、清算できる形かを問う。

    当否と形を 1 問に混ぜると、材料が無い時点ではすべて「まだ分からない」に
    倒れたため (#1436)、照合の判定 ``CheckVerdict`` とは別の型にしている。
    """

    SETTLEABLE = "settleable"
    TRUE_EITHER_WAY = "true_either_way"
    OWN_ACTION = "own_action"
    NOT_AN_EXPECTATION = "not_an_expectation"

    @property
    def is_settleable(self) -> bool:
        return self is ShapeVerdict.SETTLEABLE


__all__ = ["ShapeVerdict"]
