"""``IntentId`` 値オブジェクト。

intent の同一性を保証する識別子。tick 全体で一意であれば実装は問わない
(int / UUID 文字列 など) が、当面は単調増加 int で十分。

設計判断: ``0`` は有効な ID として許容する。「未割当」を表すセンチネルが必要な
場合は ``Optional[IntentId]`` で表現すること。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.intent.exception.intent_exception import (
    IntentIdValidationException,
)


@dataclass(frozen=True)
class IntentId:
    """intent の一意識別子。"""

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise IntentIdValidationException(
                "IntentId.value must be int (got %r)" % (type(self.value),)
            )
        if self.value < 0:
            raise IntentIdValidationException(
                f"IntentId.value must be >= 0 (got {self.value})"
            )
