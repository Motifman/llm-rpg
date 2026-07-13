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


class GoalUpdateTextTooLongException(GoalDomainException, ValidationException):
    """goal_update (自筆の言い直し) の目的文が入口の上限を超えた例外。

    VO (``GoalEntry``) の上限は健全性チェックまで緩めたため (HIGH-1 回帰対応)、
    「エージェント自筆の目的は短い命題であるべき」という制約はこの例外で
    goal_update の入口 (GoalRevisionApplier) が守る。
    """

    error_code = "GOAL.GOAL_UPDATE_TEXT_TOO_LONG"


__all__ = [
    "GoalDomainException",
    "GoalEntryValidationException",
    "GoalUpdateTextTooLongException",
]
