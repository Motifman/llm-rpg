"""Goal (目的層) ドメイン例外群。

P5 (目的層 goal_layer_design_active_inference.md G1): 目的を「取り下げない
選好的予測」として per-Being の journal に保持する。他コンテキスト
(episodic / semantic) と同じく ``GoalDomainException`` 配下の
``ValidationException`` として集約する。
"""

from ai_rpg_world.domain.common.exception import DomainException, ValidationException


class GoalDomainException(DomainException):
    """Goal (目的層) ドメインの基底例外。"""


class GoalEntryValidationException(GoalDomainException, ValidationException):
    """``GoalEntry`` のバリデーション例外 (不正な status / origin / tick 等)。"""

    error_code = "GOAL.GOAL_ENTRY_VALIDATION"


__all__ = [
    "GoalDomainException",
    "GoalEntryValidationException",
]
