"""BeingId 値オブジェクトのバリデーション挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingIdValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class TestBeingIdValidation:
    """BeingId のバリデーション挙動。"""

    def test_有効な文字列で生成できる(self) -> None:
        """非空文字列を渡せばインスタンス化される。"""
        being_id = BeingId("ada")
        assert being_id.value == "ada"

    def test_空文字なら_BeingIdValidationException_を投げる(self) -> None:
        """空文字列は不許可。"""
        with pytest.raises(BeingIdValidationException):
            BeingId("")

    def test_空白のみなら_BeingIdValidationException_を投げる(self) -> None:
        """空白のみの文字列は実質空とみなし不許可。"""
        with pytest.raises(BeingIdValidationException):
            BeingId("   ")

    def test_前後の空白はトリムされる(self) -> None:
        """前後の空白は __post_init__ でトリムされる。"""
        being_id = BeingId("  ada  ")
        assert being_id.value == "ada"

    def test_非文字列を渡すと_BeingIdValidationException_を投げる(self) -> None:
        """型違反は ValidationException として扱う。"""
        with pytest.raises(BeingIdValidationException):
            BeingId(123)  # type: ignore[arg-type]


class TestBeingIdEquality:
    """BeingId の等価性挙動 (frozen dataclass)。"""

    def test_同じ_value_なら等しい(self) -> None:
        """value 同値なら ``==`` が True。"""
        assert BeingId("ada") == BeingId("ada")

    def test_異なる_value_なら等しくない(self) -> None:
        """value が違えば等しくない。"""
        assert BeingId("ada") != BeingId("ben")

    def test_hashable(self) -> None:
        """frozen dataclass なので set / dict キーとして使える。"""
        a = BeingId("ada")
        s = {a, BeingId("ada"), BeingId("ben")}
        assert len(s) == 2

    def test_str_で_value_が返る(self) -> None:
        """``str()`` で value 文字列が返る。"""
        assert str(BeingId("ada")) == "ada"
