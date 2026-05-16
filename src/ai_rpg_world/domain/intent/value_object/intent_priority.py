"""``IntentPriority`` 値オブジェクト。

同一フェーズ内でさらに細かい解決順を決めるための数値。値が大きいほど先に
解決される (例: 高敏捷キャラが先に殴る)。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.intent.exception.intent_exception import (
    IntentPriorityValidationException,
)


@dataclass(frozen=True, order=True)
class IntentPriority:
    """整数の優先度。"""

    value: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise IntentPriorityValidationException(
                "IntentPriority.value must be int (got %r)" % (type(self.value),)
            )
