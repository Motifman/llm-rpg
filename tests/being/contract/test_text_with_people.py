"""人のプレースホルダーを持つ観測の本文 (``TextWithPeople``) と、そこに入る人の印の決まりを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.contract import ContractViolation, PersonInText, TextWithPeople, UnidentifiedPerson


def _stranger(handle: int = 3) -> PersonInText:
    return PersonInText(handle=handle, appearance="背の高い男", visible_name=None)


class TestPersonInText:
    """PersonInText が、環境の中で 1 人を指す番号・見た目・見えている名前の決まりを守ることを保証する。"""

    def test_person_with_a_visible_name_keeps_handle_appearance_and_name(self) -> None:
        """番号 0、見た目、見えている名前を渡すと、そのまま持つ。"""
        person = PersonInText(handle=0, appearance="赤い外套の女", visible_name="ミナ")

        assert (person.handle, person.appearance, person.visible_name) == (0, "赤い外套の女", "ミナ")

    @pytest.mark.parametrize("handle", [-1, True, 1.0])
    def test_handle_other_than_a_non_negative_int_is_refused(self, handle: object) -> None:
        """番号に負の数・真偽値・小数を渡すと ContractViolation を投げる。"""
        with pytest.raises(ContractViolation):
            PersonInText(handle=handle, appearance="背の高い男", visible_name=None)  # type: ignore[arg-type]

    def test_blank_appearance_is_refused(self) -> None:
        """見た目が空白だけなら ContractViolation を投げる。"""
        with pytest.raises(ContractViolation):
            PersonInText(handle=3, appearance=" ", visible_name=None)

    def test_blank_visible_name_is_refused(self) -> None:
        """見えている名前を空白だけで渡すと ContractViolation を投げる。名前が見えないときは None を渡す。"""
        with pytest.raises(ContractViolation):
            PersonInText(handle=3, appearance="背の高い男", visible_name="")


class TestTextWithPeople:
    """TextWithPeople が、文のプレースホルダーと人の対応が過不足なく揃うときだけ作れることを保証する。"""

    def test_placeholders_and_people_that_match_make_a_text(self) -> None:
        """{actor} と {target} の文に、actor に人の印、target に見分けのつかない人を当てると作れる。"""
        text = TextWithPeople(
            template="{actor}が{target}の荷に手を入れた",
            people={"actor": _stranger(), "target": UnidentifiedPerson()},
        )

        assert text.people == {"actor": _stranger(), "target": UnidentifiedPerson()}

    def test_people_cannot_be_changed_after_construction(self) -> None:
        """作ったあとに people へ人を足そうとすると TypeError になり、渡した dict を変えても中身は変わらない。"""
        given = {"actor": _stranger()}
        text = TextWithPeople(template="{actor}が扉を開けた", people=given)
        given["target"] = _stranger(4)

        with pytest.raises(TypeError):
            text.people["target"] = _stranger(4)  # type: ignore[index]
        assert set(text.people) == {"actor"}

    def test_text_without_placeholders_needs_no_people(self) -> None:
        """プレースホルダーの無い文は、人を当てずに作れる。"""
        assert TextWithPeople(template="遠くで鐘が鳴った", people={}).people == {}

    def test_placeholder_without_a_person_is_refused(self) -> None:
        """{target} に人を当てていなければ ContractViolation を投げる。"""
        with pytest.raises(ContractViolation):
            TextWithPeople(template="{actor}が{target}を呼んだ", people={"actor": _stranger()})

    def test_person_without_a_placeholder_is_refused(self) -> None:
        """文に無い target に人を当てると ContractViolation を投げる。"""
        with pytest.raises(ContractViolation):
            TextWithPeople(template="{actor}が扉を開けた", people={"actor": _stranger(), "target": _stranger(4)})

    @pytest.mark.parametrize(
        ("template", "key"),
        [
            ("{}が来た", ""),
            ("{0}が来た", "0"),
            ("{actor!r}が来た", "actor"),
            ("{actor:>3}が来た", "actor"),
            ("{actor:}が来た", "actor"),
            ("{actor.name}が来た", "actor.name"),
            ("{actor が来た", "actor"),
        ],
    )
    def test_placeholder_other_than_a_named_person_is_refused(self, template: str, key: str) -> None:
        """位置・変換・書式指定 (空の書式指定を含む)・属性のプレースホルダーと閉じていない括弧は、同じ鍵で人を当てても ContractViolation を投げる。"""
        with pytest.raises(ContractViolation):
            TextWithPeople(template=template, people={key: _stranger()})

    def test_doubled_braces_are_literal_braces(self) -> None:
        """{{ と }} は文字の括弧で、プレースホルダーとして数えない。"""
        text = TextWithPeople(template="{actor}が「{{合図}}」と書いた", people={"actor": _stranger()})

        assert set(text.people) == {"actor"}

    def test_blank_template_is_refused(self) -> None:
        """文が空白だけなら ContractViolation を投げる。"""
        with pytest.raises(ContractViolation):
            TextWithPeople(template="  ", people={})

    def test_person_of_another_type_is_refused(self) -> None:
        """人の印の代わりに名前の文字列を当てると ContractViolation を投げる。"""
        with pytest.raises(ContractViolation):
            TextWithPeople(template="{actor}が来た", people={"actor": "カイ"})  # type: ignore[dict-item]
