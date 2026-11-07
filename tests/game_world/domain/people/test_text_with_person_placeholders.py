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
    TextWithPersonPlaceholders,
    Unidentified,
)


def _ref(handle: int) -> PersonRef:
    return PersonRef(handle=PersonHandle(handle), appearance="旅装の女", visible_name=NoVisibleName())


class TestTextWithPersonPlaceholders:
    """TextWithPersonPlaceholders が、作者の書いた人のプレースホルダーのある文を持ち、人を渡されて TextWithPeople になることを保証する。"""

    def test_placeholders_are_the_named_person_placeholders(self) -> None:
        """placeholders は文のプレースホルダーの名前を、重なりを除いて答える。"""
        text = TextWithPersonPlaceholders("{actor}が{target}を起こし、{actor}は去った。")

        assert text.placeholders() == frozenset({"actor", "target"})

    def test_text_without_placeholders_has_no_placeholders(self) -> None:
        """プレースホルダーの無い文の placeholders は空。"""
        assert TextWithPersonPlaceholders("扉が軋んだ。").placeholders() == frozenset()

    def test_fill_pairs_each_placeholder_with_a_person(self) -> None:
        """fill にプレースホルダーごとの人を渡すと、同じ文と人を持つ TextWithPeople になる。"""
        filled = TextWithPersonPlaceholders("{person}は昇降機で外へ出た。").fill({"person": Unidentified()})

        assert filled == TextWithPeople(template="{person}は昇降機で外へ出た。", people={"person": Unidentified()})

    def test_fill_without_placeholders_takes_no_people(self) -> None:
        """プレースホルダーの無い文は、空の people で fill できる。"""
        assert TextWithPersonPlaceholders("扉が軋んだ。").fill({}) == TextWithPeople(template="扉が軋んだ。", people={})

    def test_fill_missing_a_person_raises_domain_exception(self) -> None:
        """プレースホルダーの人が欠けた people で fill すると PlaceholdersAndPeopleMismatchException を投げる。"""
        with pytest.raises(PlaceholdersAndPeopleMismatchException):
            TextWithPersonPlaceholders("{actor}が{target}を起こした。").fill({"actor": _ref(1)})

    def test_fill_with_an_extra_person_raises_domain_exception(self) -> None:
        """文に無いプレースホルダーの人を含む people で fill すると PlaceholdersAndPeopleMismatchException を投げる。"""
        with pytest.raises(PlaceholdersAndPeopleMismatchException):
            TextWithPersonPlaceholders("{actor}が座った。").fill({"actor": _ref(1), "target": _ref(2)})

    @pytest.mark.parametrize(
        "template",
        ["{}が座った。", "{0}が座った。", "{actor!r}が座った。", "{object.name}を開けた。", "{actor が座った。"],
    )
    def test_malformed_placeholder_is_refused_when_declared(self, template: str) -> None:
        """名前の付いた人のプレースホルダーでない書き方を含む文は、作るときに MalformedTemplateException を投げる。シナリオの読み込みで書き間違いを止めるため。"""
        with pytest.raises(MalformedTemplateException):
            TextWithPersonPlaceholders(template)
