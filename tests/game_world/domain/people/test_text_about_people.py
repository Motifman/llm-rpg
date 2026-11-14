from __future__ import annotations

from collections.abc import Mapping

import pytest

from ai_rpg_world.game_world.domain.exception.people_exception import PlaceholdersAndPeopleMismatchException
from ai_rpg_world.game_world.domain.people import (
    NoVisibleName,
    PeopleAsSeen,
    PersonHandle,
    PersonRef,
    TextAboutPeople,
    TextWithAssignedPeople,
    TextWithUnassignedPeople,
    Unidentified,
)
from ai_rpg_world.game_world.domain.value_object import PersonId

_ALICE = PersonId("alice")
_BOB = PersonId("bob")
_WOKE_UP = TextWithUnassignedPeople("{actor}が{target}を起こした。")


def _ref(handle: int, appearance: str) -> PersonRef:
    return PersonRef(handle=PersonHandle(handle), appearance=appearance, visible_name=NoVisibleName())


class _ViewFromOnePerson(PeopleAsSeen):
    def __init__(self, refs: Mapping[PersonId, PersonRef]) -> None:
        self._refs = refs

    def ref_of(self, person: PersonId) -> PersonRef:
        return self._refs[person]


class TestAbout:
    """TextWithUnassignedPeople.about が、プレースホルダーに誰のことかだけを当てた文を作ることを保証する。"""

    def test_about_pairs_each_placeholder_with_a_person_id(self) -> None:
        """「{actor}が{target}を起こした。」に actor=alice、target=bob を当てると、同じ文と人を持つ TextAboutPeople になる。"""
        about = _WOKE_UP.about({"actor": _ALICE, "target": _BOB})

        assert about == TextAboutPeople(template=_WOKE_UP, people={"actor": _ALICE, "target": _BOB})

    def test_about_missing_a_person_raises_domain_exception(self) -> None:
        """プレースホルダーの人が欠けた people で about すると PlaceholdersAndPeopleMismatchException を投げる。"""
        with pytest.raises(PlaceholdersAndPeopleMismatchException):
            _WOKE_UP.about({"actor": _ALICE})


class TestTextAboutPeople:
    """TextAboutPeople が、プレースホルダーと人の鍵の揃いを作るときに確かめ、見る人ごとの呼び方を当てた文にすることを保証する。"""

    def test_explains_is_true(self) -> None:
        """人を当てはめた文は失敗を説明する文があるので、explains は True を返す。"""
        assert _WOKE_UP.about({"actor": _ALICE, "target": _BOB}).explains() is True

    def test_extra_person_is_refused_when_made(self) -> None:
        """文に無いプレースホルダーの人を含む people で作ると PlaceholdersAndPeopleMismatchException を投げる。"""
        with pytest.raises(PlaceholdersAndPeopleMismatchException):
            TextAboutPeople(
                template=TextWithUnassignedPeople("{actor}が座った。"), people={"actor": _ALICE, "target": _BOB}
            )

    def test_missing_person_is_refused_when_made(self) -> None:
        """プレースホルダーの人が欠けた people で作ると PlaceholdersAndPeopleMismatchException を投げる。"""
        with pytest.raises(PlaceholdersAndPeopleMismatchException):
            TextAboutPeople(template=_WOKE_UP, people={"actor": _ALICE})

    def test_seen_by_assigns_the_viewer_s_refs(self) -> None:
        """alice が bob を起こした文を、alice を「旅装の女」、bob を「髭の男」と見る人に見せると、その呼び方を当てた文になる。"""
        about = _WOKE_UP.about({"actor": _ALICE, "target": _BOB})
        traveller = _ref(1, "旅装の女")
        bearded = _ref(2, "髭の男")
        view = _ViewFromOnePerson({_ALICE: traveller, _BOB: bearded})

        assert about.seen_by(view) == TextWithAssignedPeople(
            template="{actor}が{target}を起こした。", people={"actor": traveller, "target": bearded}
        )

    def test_same_text_is_seen_differently_by_different_viewers(self) -> None:
        """同じ文を、alice の呼び方が違う 2 人に見せると、それぞれの呼び方の文になる。"""
        about = TextWithUnassignedPeople("{actor}が座った。").about({"actor": _ALICE})
        first_view = _ViewFromOnePerson({_ALICE: _ref(1, "旅装の女")})
        second_view = _ViewFromOnePerson({_ALICE: _ref(7, "外套の人")})

        assert about.seen_by(first_view).people["actor"] == _ref(1, "旅装の女")
        assert about.seen_by(second_view).people["actor"] == _ref(7, "外套の人")

    def test_unidentified_assigns_no_one_recognizable(self) -> None:
        """unidentified は、どのプレースホルダーにも見分けのつかない人 (Unidentified) を当てる。"""
        about = _WOKE_UP.about({"actor": _ALICE, "target": _BOB})

        assert about.unidentified() == TextWithAssignedPeople(
            template="{actor}が{target}を起こした。", people={"actor": Unidentified(), "target": Unidentified()}
        )
