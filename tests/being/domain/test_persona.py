"""Persona が、名前だけを必須にし、決まっていない人柄を仮の値で埋めずに持つことを保証する。"""

from __future__ import annotations

import dataclasses

import pytest

from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.exception.being_exceptions import PersonaValidationException


class TestPersonaFields:
    """名前と人柄の各項目の受け取り方を保証する。"""

    def test_only_name_leaves_the_rest_undecided(self) -> None:
        """名前だけを渡すと、一人称・口調・生い立ちは None、性格・大事にしていること・怖いものは空のまま。"""
        persona = Persona(name="ハル")

        assert persona == Persona(
            name="ハル", first_person=None, speech=None, traits=(), values=(), fears=(), background=None
        )

    def test_text_fields_are_stripped(self) -> None:
        """名前と人柄の文は、前後の空白を除いて持つ。"""
        persona = Persona(
            name=" ハル ",
            first_person=" 俺 ",
            speech=" 落ち着いた常体 ",
            traits=(" 慎重 ",),
            values=(" 仲間 ",),
            fears=(" 暗闇 ",),
            background=" 測量隊の隊長 ",
        )

        assert persona == Persona(
            name="ハル",
            first_person="俺",
            speech="落ち着いた常体",
            traits=("慎重",),
            values=("仲間",),
            fears=("暗闇",),
            background="測量隊の隊長",
        )

    @pytest.mark.parametrize("field_name", ["name", "first_person", "speech", "background"])
    @pytest.mark.parametrize("value", ["", "   ", 1])
    def test_blank_or_non_text_raises(self, field_name: str, value: object) -> None:
        """名前と人柄の文に、空白だけの文字列か文字列でない値を渡すと PersonaValidationException を投げる。"""
        fields: dict[str, object] = {"name": "ハル", field_name: value}

        with pytest.raises(PersonaValidationException, match=field_name):
            Persona(**fields)  # type: ignore[arg-type]

    @pytest.mark.parametrize("field_name", ["traits", "values", "fears"])
    @pytest.mark.parametrize("value", [["慎重"], ("慎重", " "), ("慎重", 1)])
    def test_list_fields_must_be_tuples_of_text(self, field_name: str, value: object) -> None:
        """性格・大事にしていること・怖いものは、空白でない文字列のタプルでなければ PersonaValidationException を投げる。"""
        with pytest.raises(PersonaValidationException, match=field_name):
            Persona(name="ハル", **{field_name: value})  # type: ignore[arg-type]

    def test_persona_cannot_be_reassigned(self) -> None:
        """人柄は値オブジェクトなので、項目を後から書き換えられない。"""
        persona = Persona(name="ハル")

        with pytest.raises(dataclasses.FrozenInstanceError):
            persona.name = "ミオ"  # type: ignore[misc]


class TestPersonaFromFields:
    """Persona.from_fields が、欄の名前の地図から人柄を作り、人柄に無い欄や名前の無い地図を断ることを保証する。"""

    def test_builds_persona_from_given_fields(self) -> None:
        """名前・一人称・怖いものの欄を渡すと、その値を持ち、渡さなかった欄は決まっていないままの人柄になる。"""
        persona = Persona.from_fields({"name": "サヨ", "first_person": "わたし", "fears": ("暗い坑道",)})

        assert persona == Persona(name="サヨ", first_person="わたし", fears=("暗い坑道",))

    def test_unknown_field_is_refused(self) -> None:
        """人柄に無い欄 (persona) があると PersonaValidationException を投げる。"""
        with pytest.raises(PersonaValidationException):
            Persona.from_fields({"name": "サヨ", "persona": "物覚えのよい娘"})

    def test_missing_name_is_refused(self) -> None:
        """名前の欄が無いと PersonaValidationException を投げる。"""
        with pytest.raises(PersonaValidationException):
            Persona.from_fields({"first_person": "わたし"})
