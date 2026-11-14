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
    TextWithAssignedPeople,
    TextWithUnassignedPeople,
    Unidentified,
)
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, PersonId


def _ref(handle: int) -> PersonRef:
    return PersonRef(handle=PersonHandle(handle), appearance=DescriptionText("旅装の女"), visible_name=NoVisibleName())


class TestTextWithUnassignedPeople:
    """TextWithUnassignedPeople が、作者の書いた人のプレースホルダーのある文を持ち、人を渡されて TextWithAssignedPeople になることを保証する。"""

    def test_placeholders_are_the_named_person_placeholders(self) -> None:
        """placeholders は文のプレースホルダーの名前を、重なりを除いて答える。"""
        text = TextWithUnassignedPeople("{actor}が{target}を起こし、{actor}は去った。")

        assert text.placeholders() == frozenset({"actor", "target"})

    def test_text_without_placeholders_has_no_placeholders(self) -> None:
        """プレースホルダーの無い文の placeholders は空。"""
        assert TextWithUnassignedPeople("扉が軋んだ。").placeholders() == frozenset()

    def test_explains_is_true(self) -> None:
        """プレースホルダーの無い文でも、文があれば失敗を説明できるので、TextWithUnassignedPeople の explains は True を返す。"""
        assert TextWithUnassignedPeople("扉が軋んだ。").explains() is True

    def test_about_each_asks_each_placeholder_with_the_template(self) -> None:
        """about_each はプレースホルダーごとに名前と文そのものを渡して人を問い合わせ、その人を当てはめた TextAboutPeople を返す。"""
        text = TextWithUnassignedPeople("{actor}が{target}を起こした。")
        asked: list[tuple[str, str]] = []

        def person_of(placeholder: str, template: str) -> PersonId:
            asked.append((placeholder, template))
            return PersonId(placeholder)

        about = text.about_each(person_of)

        assert sorted(asked) == [("actor", text.template), ("target", text.template)]
        assert about == text.about({"actor": PersonId("actor"), "target": PersonId("target")})

    def test_placeholders_read_as_collects_what_each_placeholder_reads_as(self) -> None:
        """placeholders_read_as はプレースホルダーごとに名前と文を読み方に渡し、読んだ値を重なりを除いた集合で返す。"""
        text = TextWithUnassignedPeople("{actor}が{target}を起こし、{actor}は去った。")

        read = text.placeholders_read_as(lambda placeholder, template: f"{placeholder}@{template}")

        assert read == frozenset({f"actor@{text.template}", f"target@{text.template}"})

    def test_assign_pairs_each_placeholder_with_a_person(self) -> None:
        """assign にプレースホルダーごとの人を渡すと、同じ文と人を持つ TextWithAssignedPeople になる。"""
        assigned = TextWithUnassignedPeople("{person}は昇降機で外へ出た。").assign({"person": Unidentified()})

        assert assigned == TextWithAssignedPeople(
            template="{person}は昇降機で外へ出た。", people={"person": Unidentified()}
        )

    def test_assign_without_placeholders_takes_no_people(self) -> None:
        """プレースホルダーの無い文は、空の people で assign できる。"""
        assert TextWithUnassignedPeople("扉が軋んだ。").assign({}) == TextWithAssignedPeople(
            template="扉が軋んだ。", people={}
        )

    def test_assign_missing_a_person_raises_domain_exception(self) -> None:
        """プレースホルダーの人が欠けた people で assign すると PlaceholdersAndPeopleMismatchException を投げる。"""
        with pytest.raises(PlaceholdersAndPeopleMismatchException):
            TextWithUnassignedPeople("{actor}が{target}を起こした。").assign({"actor": _ref(1)})

    def test_assign_with_an_extra_person_raises_domain_exception(self) -> None:
        """文に無いプレースホルダーの人を含む people で assign すると PlaceholdersAndPeopleMismatchException を投げる。"""
        with pytest.raises(PlaceholdersAndPeopleMismatchException):
            TextWithUnassignedPeople("{actor}が座った。").assign({"actor": _ref(1), "target": _ref(2)})

    @pytest.mark.parametrize(
        "template",
        ["{}が座った。", "{0}が座った。", "{actor!r}が座った。", "{object.name}を開けた。", "{actor が座った。"],
    )
    def test_malformed_placeholder_is_refused_when_declared(self, template: str) -> None:
        """名前の付いた人のプレースホルダーでない書き方を含む文は、作るときに MalformedTemplateException を投げる。シナリオの読み込みで書き間違いを止めるため。"""
        with pytest.raises(MalformedTemplateException):
            TextWithUnassignedPeople(template)
