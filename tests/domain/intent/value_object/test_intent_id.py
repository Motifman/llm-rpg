"""``IntentId`` 値オブジェクトのバリデーション挙動。"""

import pytest

from ai_rpg_world.domain.intent.exception.intent_exception import (
    IntentIdValidationException,
)
from ai_rpg_world.domain.intent.value_object.intent_id import IntentId


class TestIntentId:
    """``IntentId`` のバリデーション挙動。"""

    def test_valid_non_negative_int_is_accepted(self) -> None:
        """0 以上の int は受理される。"""
        assert IntentId(0).value == 0
        assert IntentId(42).value == 42

    def test_negative_int_is_rejected(self) -> None:
        """負の int は IntentIdValidationException を投げる。"""
        with pytest.raises(IntentIdValidationException):
            IntentId(-1)

    def test_non_int_is_rejected(self) -> None:
        """int 以外は弾かれる。"""
        with pytest.raises(IntentIdValidationException):
            IntentId("0")  # type: ignore[arg-type]

    def test_bool_is_rejected(self) -> None:
        """bool は int の subtype だが意図的に弾く。"""
        with pytest.raises(IntentIdValidationException):
            IntentId(True)  # type: ignore[arg-type]

    def test_equality_uses_value(self) -> None:
        """frozen dataclass なので value 等価で == が成立する。"""
        assert IntentId(7) == IntentId(7)
        assert IntentId(7) != IntentId(8)
