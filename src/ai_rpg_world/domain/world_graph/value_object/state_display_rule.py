"""SpotObject.state の値を prompt 用の作者文言へ変換する表示ルール。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    StateDisplayRuleValidationException,
)

_ALLOWED_VALUE_TYPES = (bool, int, float, str, type(None))


def state_display_value_identity(value: Any) -> tuple[type, Any]:
    """state_display の値比較で使う、型を含む同一性キーを返す。

    Python では ``False == 0`` / ``True == 1`` が成り立つ。表示ルールでは
    bool state と数値 state は別概念なので、型を比較キーに含めて誤爆を防ぐ。
    """

    return (type(value), value)


def state_display_values_equal(left: Any, right: Any) -> bool:
    """state_display の値を、bool と 0/1 を混同しない形で比較する。"""

    return state_display_value_identity(left) == state_display_value_identity(right)


@dataclass(frozen=True)
class StateDisplayRule:
    """SpotObject.state の特定 key/value を prompt 用 tag 文言へ変換する。"""

    key: str
    value: Any
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise StateDisplayRuleValidationException(
                "StateDisplayRule.key must be a non-empty string"
            )
        if type(self.value) not in _ALLOWED_VALUE_TYPES:
            raise StateDisplayRuleValidationException(
                "StateDisplayRule.value must be a JSON primitive "
                "(bool, int, float, str, or null)"
            )
        if not isinstance(self.text, str) or not self.text.strip():
            raise StateDisplayRuleValidationException(
                "StateDisplayRule.text must be a non-empty string"
            )
