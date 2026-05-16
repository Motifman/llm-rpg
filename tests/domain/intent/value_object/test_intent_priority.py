"""``IntentPriority`` のバリデーション挙動。"""

import pytest

from ai_rpg_world.domain.intent.exception.intent_exception import (
    IntentPriorityValidationException,
)
from ai_rpg_world.domain.intent.value_object.intent_priority import (
    IntentPriority,
)


class TestIntentPriority:
    """``IntentPriority`` のバリデーション挙動。"""

    def test_default_value_is_zero(self) -> None:
        """既定値は 0。"""
        assert IntentPriority().value == 0

    def test_negative_value_is_accepted(self) -> None:
        """負の優先度も意味があるので許容する (低優先 = 後回し)。"""
        assert IntentPriority(-5).value == -5

    def test_non_int_is_rejected(self) -> None:
        """int 以外は弾く。"""
        with pytest.raises(IntentPriorityValidationException):
            IntentPriority("high")  # type: ignore[arg-type]

    def test_bool_is_rejected(self) -> None:
        """bool は弾く。"""
        with pytest.raises(IntentPriorityValidationException):
            IntentPriority(True)  # type: ignore[arg-type]

    def test_order_comparison(self) -> None:
        """値の大小で比較できる (dataclass(order=True))。"""
        assert IntentPriority(1) < IntentPriority(2)
        assert IntentPriority(5) > IntentPriority(0)
