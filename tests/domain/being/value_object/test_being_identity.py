"""BeingIdentity 値オブジェクトのバリデーション挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingIdentityValidationException,
)
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity


class TestBeingIdentityValidation:
    """BeingIdentity の不変核バリデーション挙動。"""

    def test_name_first_person_can_create(self) -> None:
        """両フィールドが非空文字列ならインスタンス化される。"""
        identity = BeingIdentity(name="アダ", first_person="わたし")
        assert identity.name == "アダ"
        assert identity.first_person == "わたし"

    def test_name_empty_being_id_entity_raises_validation_exception(self) -> None:
        """name の空文字は不許可。"""
        with pytest.raises(BeingIdentityValidationException):
            BeingIdentity(name="", first_person="わたし")

    def test_first_person_empty_being_id_entity_raises_validation_exception(
        self,
    ) -> None:
        """first_person の空文字は不許可。"""
        with pytest.raises(BeingIdentityValidationException):
            BeingIdentity(name="アダ", first_person="")

    def test_name_blank_raises_exception(self) -> None:
        """空白のみは実質空とみなし不許可。"""
        with pytest.raises(BeingIdentityValidationException):
            BeingIdentity(name="   ", first_person="わたし")

    def test_name_around_blank(self) -> None:
        """name は前後の空白がトリムされる。"""
        identity = BeingIdentity(name="  アダ  ", first_person="わたし")
        assert identity.name == "アダ"

    def test_case_raises_exception(self) -> None:
        """型違反は ValidationException として扱う。"""
        with pytest.raises(BeingIdentityValidationException):
            BeingIdentity(name=123, first_person="わたし")  # type: ignore[arg-type]


class TestBeingIdentityEquality:
    """BeingIdentity の等価性挙動。"""

    def test_same_equals(self) -> None:
        """name / first_person 同値なら ``==`` が True。"""
        assert BeingIdentity(name="アダ", first_person="わたし") == BeingIdentity(
            name="アダ", first_person="わたし"
        )

    def test_first_person_not_equal(self) -> None:
        """first_person が違えば等しくない。"""
        assert BeingIdentity(name="アダ", first_person="わたし") != BeingIdentity(
            name="アダ", first_person="俺"
        )
