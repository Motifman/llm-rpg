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

    @pytest.mark.parametrize("field_name", ["name", "first_person"])
    def test_blank_identity_field_is_rejected(self, field_name: str) -> None:
        """名前・一人称のどちらかが空白だけなら、その項目の検証例外になる。"""
        values = {"name": "アダ", "first_person": "わたし"}
        values[field_name] = "   "
        with pytest.raises(BeingIdentityValidationException, match=field_name):
            BeingIdentity(**values)

    @pytest.mark.parametrize("field_name", ["name", "first_person"])
    def test_identity_field_whitespace_is_trimmed(self, field_name: str) -> None:
        """名前・一人称の前後空白は除き、もう一方の内容は変えない。"""
        values = {"name": "アダ", "first_person": "わたし"}
        values[field_name] = f"  {values[field_name]}  "
        identity = BeingIdentity(**values)
        assert identity.name == "アダ"
        assert identity.first_person == "わたし"

    @pytest.mark.parametrize("field_name", ["name", "first_person"])
    def test_non_string_identity_field_is_rejected(self, field_name: str) -> None:
        """名前・一人称の数値入力は暗黙に文字列化せず、その項目の検証例外にする。"""
        values: dict[str, str | int] = {"name": "アダ", "first_person": "わたし"}
        values[field_name] = 123
        with pytest.raises(BeingIdentityValidationException, match=field_name):
            BeingIdentity(**values)  # type: ignore[arg-type]


class TestBeingIdentityEquality:
    """BeingIdentity の等価性挙動。"""

    def test_same_equals(self) -> None:
        """name / first_person 同値なら ``==`` が True。"""
        assert BeingIdentity(name="アダ", first_person="わたし") == BeingIdentity(name="アダ", first_person="わたし")

    @pytest.mark.parametrize("name, first_person", [("ベン", "わたし"), ("アダ", "俺")])
    def test_different_identity_field_is_not_equal(self, name: str, first_person: str) -> None:
        """名前・一人称の一方だけが違っても、同じ人格核ではない。"""
        assert BeingIdentity(name="アダ", first_person="わたし") != BeingIdentity(name=name, first_person=first_person)


class TestBeingIdentityImmutability:
    """人格の不変核は外部から項目を書き換えて変えられない。"""

    @pytest.mark.parametrize("field_name", ["name", "first_person"])
    def test_identity_fields_cannot_be_reassigned(self, field_name: str) -> None:
        """名前・一人称への外部代入を拒否し、両項目の元値を保つ。"""
        identity = BeingIdentity(name="アダ", first_person="わたし")
        with pytest.raises(AttributeError):
            setattr(identity, field_name, "変更後")
        assert identity.name == "アダ"
        assert identity.first_person == "わたし"
