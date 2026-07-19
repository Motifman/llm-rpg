"""BeingId 値オブジェクトのバリデーション挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingIdValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class TestBeingIdValidation:
    """BeingId のバリデーション挙動。"""

    def test_string_can_create(self) -> None:
        """非空文字列を渡せばインスタンス化される。"""
        being_id = BeingId("ada")
        assert being_id.value == "ada"

    def test_empty_string_being_id_raises_validation_exception(self) -> None:
        """空文字列は不許可。"""
        with pytest.raises(BeingIdValidationException):
            BeingId("")

    def test_blank_being_id_raises_validation_exception(self) -> None:
        """空白のみの文字列は実質空とみなし不許可。"""
        with pytest.raises(BeingIdValidationException):
            BeingId("   ")

    def test_around_blank(self) -> None:
        """前後の空白は __post_init__ でトリムされる。"""
        being_id = BeingId("  ada  ")
        assert being_id.value == "ada"

    def test_being_id_raises_validation_exception(self) -> None:
        """型違反は ValidationException として扱う。"""
        with pytest.raises(BeingIdValidationException):
            BeingId(123)  # type: ignore[arg-type]


class TestBeingIdEquality:
    """BeingId の等価性挙動 (frozen dataclass)。"""

    def test_same_value_equals(self) -> None:
        """value 同値なら ``==`` が True。"""
        assert BeingId("ada") == BeingId("ada")

    def test_value_not_equal(self) -> None:
        """value が違えば等しくない。"""
        assert BeingId("ada") != BeingId("ben")

    def test_hashable(self) -> None:
        """frozen dataclass なので set / dict キーとして使える。"""
        a = BeingId("ada")
        s = {a, BeingId("ada"), BeingId("ben")}
        assert len(s) == 2

    def test_returns_str_value(self) -> None:
        """``str()`` で value 文字列が返る。"""
        assert str(BeingId("ada")) == "ada"
