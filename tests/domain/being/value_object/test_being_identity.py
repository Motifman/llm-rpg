"""BeingIdentity 値オブジェクトのバリデーション挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingIdentityValidationException,
)
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity


class TestBeingIdentityValidation:
    """BeingIdentity の不変核バリデーション挙動。"""

    def test_有効な_name_と_first_person_で生成できる(self) -> None:
        """両フィールドが非空文字列ならインスタンス化される。"""
        identity = BeingIdentity(name="アダ", first_person="わたし")
        assert identity.name == "アダ"
        assert identity.first_person == "わたし"

    def test_name_が空なら_BeingIdentityValidationException_を投げる(self) -> None:
        """name の空文字は不許可。"""
        with pytest.raises(BeingIdentityValidationException):
            BeingIdentity(name="", first_person="わたし")

    def test_first_person_が空なら_BeingIdentityValidationException_を投げる(
        self,
    ) -> None:
        """first_person の空文字は不許可。"""
        with pytest.raises(BeingIdentityValidationException):
            BeingIdentity(name="アダ", first_person="")

    def test_name_が空白のみなら_例外を投げる(self) -> None:
        """空白のみは実質空とみなし不許可。"""
        with pytest.raises(BeingIdentityValidationException):
            BeingIdentity(name="   ", first_person="わたし")

    def test_name_の前後空白はトリムされる(self) -> None:
        """name は前後の空白がトリムされる。"""
        identity = BeingIdentity(name="  アダ  ", first_person="わたし")
        assert identity.name == "アダ"

    def test_非文字列を渡すと_例外を投げる(self) -> None:
        """型違反は ValidationException として扱う。"""
        with pytest.raises(BeingIdentityValidationException):
            BeingIdentity(name=123, first_person="わたし")  # type: ignore[arg-type]


class TestBeingIdentityEquality:
    """BeingIdentity の等価性挙動。"""

    def test_同じフィールドなら等しい(self) -> None:
        """name / first_person 同値なら ``==`` が True。"""
        assert BeingIdentity(name="アダ", first_person="わたし") == BeingIdentity(
            name="アダ", first_person="わたし"
        )

    def test_異なる_first_person_なら等しくない(self) -> None:
        """first_person が違えば等しくない。"""
        assert BeingIdentity(name="アダ", first_person="わたし") != BeingIdentity(
            name="アダ", first_person="俺"
        )
