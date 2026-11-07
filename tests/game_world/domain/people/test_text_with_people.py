from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.people_exception import (
    MalformedTemplateException,
    PlaceholdersAndPeopleMismatchException,
)
from ai_rpg_world.game_world.domain.people import (
    NoVisibleName,
    PersonHandle,
    PersonRef,
    TextWithPeople,
    Unidentified,
)


def _ref(handle: int) -> PersonRef:
    return PersonRef(handle=PersonHandle(handle), appearance="旅装の女", visible_name=NoVisibleName())


class TestTextWithPeoplePlaceholders:
    """TextWithPeople の文の人のプレースホルダーと、people の鍵が過不足なく揃っていることを保証する。"""

    def test_text_without_placeholders_needs_no_people(self) -> None:
        """プレースホルダーの無い文は、people を空にして作れる。"""
        text = TextWithPeople(template="扉が軋んだ。", people={})

        assert text.people == {}

    def test_each_placeholder_is_paired_with_a_person(self) -> None:
        """{actor} と {target} のプレースホルダーに、それぞれ PersonRef と Unidentified を渡して作れる。"""
        text = TextWithPeople(
            template="{actor}が{target}に薬を渡した。",
            people={"actor": _ref(1), "target": Unidentified()},
        )

        assert text.people == {"actor": _ref(1), "target": Unidentified()}

    def test_placeholder_used_twice_needs_one_person(self) -> None:
        """同じプレースホルダーを 2 度使う文は、そのプレースホルダーの人を 1 人だけ持てばよい。"""
        text = TextWithPeople(template="{actor}は{actor}の荷を下ろした。", people={"actor": _ref(1)})

        assert text.people == {"actor": _ref(1)}

    def test_placeholder_without_person_raises_domain_exception(self) -> None:
        """プレースホルダーがあるのに people にその人が無いと PlaceholdersAndPeopleMismatchException を投げる。Being に埋まらないプレースホルダーが渡らないため。"""
        with pytest.raises(PlaceholdersAndPeopleMismatchException):
            TextWithPeople(template="{actor}が{target}を起こした。", people={"actor": _ref(1)})

    def test_person_without_placeholder_raises_domain_exception(self) -> None:
        """people に文に無いプレースホルダーの人があると PlaceholdersAndPeopleMismatchException を投げる。書き間違えたプレースホルダーの名前を見逃さないため。"""
        with pytest.raises(PlaceholdersAndPeopleMismatchException):
            TextWithPeople(template="扉が軋んだ。", people={"actor": _ref(1)})

    def test_escaped_braces_are_text_not_placeholders(self) -> None:
        """{{ と }} は文字の括弧として扱い、プレースホルダーにしない。"""
        text = TextWithPeople(template="壁に{{印}}が刻まれている。", people={})

        assert text.template == "壁に{{印}}が刻まれている。"

    def test_people_given_later_change_does_not_reach_the_text(self) -> None:
        """作ったあとに渡した dict を書き換えても、TextWithPeople の人は変わらない。"""
        people = {"actor": _ref(1)}
        text = TextWithPeople(template="{actor}が座った。", people=people)

        people["actor"] = _ref(2)

        assert text.people == {"actor": _ref(1)}

    def test_equal_template_and_people_are_equal(self) -> None:
        """文と人が同じ TextWithPeople どうしは等しい。"""
        assert TextWithPeople(template="{actor}が座った。", people={"actor": _ref(1)}) == TextWithPeople(
            template="{actor}が座った。", people={"actor": _ref(1)}
        )


class TestTextWithPeopleMalformedTemplate:
    """TextWithPeople のプレースホルダーが、名前の付いた人のプレースホルダーの書き方だけを受け付けることを保証する。"""

    @pytest.mark.parametrize(
        "template",
        [
            "{}が座った。",
            "{0}が座った。",
            "{actor!r}が座った。",
            "{actor:>3}が座った。",
            "{actor:}が座った。",
            "{actor:{target}}が座った。",
            "{actor.name}が座った。",
            "{actor[0]}が座った。",
            "{actor が座った。",
            "actor} が座った。",
        ],
    )
    def test_placeholder_not_named_after_a_person_raises_domain_exception(self, template: str) -> None:
        """位置のプレースホルダー、変換、書式指定、属性や添字、閉じていない括弧を含む文は MalformedTemplateException を投げる。プレースホルダーは人だけで、人の中身を文が読みに行かないため。"""
        with pytest.raises(MalformedTemplateException):
            TextWithPeople(template=template, people={"actor": _ref(1)})
