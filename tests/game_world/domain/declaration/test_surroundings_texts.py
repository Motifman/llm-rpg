from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SurroundingsTexts
from ai_rpg_world.game_world.domain.exception.surroundings_texts_exception import (
    BlankPeopleJoinerException,
    NoPeopleToListException,
    PeopleNotWrittenOnceException,
    PersonInSurroundingsNoticeException,
)
from ai_rpg_world.game_world.domain.people import PersonRef, TextWithUnassignedPeople, Unidentified
from ai_rpg_world.game_world.domain.people.person_handle import PersonHandle
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName
from tests.game_world.support.world_design_for_tests import scene_texts


def _seen(handle: int, name: str) -> PersonRef:
    return PersonRef(handle=PersonHandle(handle), appearance=DescriptionText("旅の人"), visible_name=DisplayName(name))


HARU = _seen(1, "haru")
NATSU = _seen(2, "natsu")
AKI = _seen(3, "aki")


def _texts(
    people_here: str = "ここには{people}がいる。",
    bodies_here: str = "{people}が倒れている。",
    joiner: str = "、",
    waking: str = "目が覚めた。",
    darkening: str = "辺りが暗くなった。",
) -> SurroundingsTexts:
    return SurroundingsTexts(
        people_here=TextWithUnassignedPeople(people_here),
        bodies_here=TextWithUnassignedPeople(bodies_here),
        joiner=joiner,
        waking=TextWithUnassignedPeople(waking),
        darkening=TextWithUnassignedPeople(darkening),
        scene=scene_texts(),
    )


def _written(text: TextWithAssignedPeople) -> str:
    return text.template.format(**{key: _name_of(person) for key, person in text.people.items()})


def _name_of(person: PersonRef | Unidentified) -> str:
    if isinstance(person, Unidentified):
        return "誰か"
    assert isinstance(person.visible_name, DisplayName)
    return person.visible_name.text


class TestPeopleListing:
    """SurroundingsTexts.scene_as_seen が {people} の穴を 1 人ずつの穴に広げ、つなぐ言葉で並べることを保証する。

    人のいない側の文は出さず、いる側の文だけを people_here、bodies_here の順につなぐ。
    """

    def test_one_person_fills_the_hole_without_joiner(self) -> None:
        """人が 1 人のとき、つなぐ言葉を使わずに「ここにはharuがいる。」になる。"""
        text = _texts().scene_as_seen(people=(HARU,), bodies=())

        assert _written(text) == "ここにはharuがいる。"

    def test_people_are_joined_in_the_given_order(self) -> None:
        """人が 3 人のとき、渡した順につなぐ言葉で並び「ここにはharu、natsu、akiがいる。」になる。"""
        text = _texts().scene_as_seen(people=(HARU, NATSU, AKI), bodies=())

        assert _written(text) == "ここにはharu、natsu、akiがいる。"

    def test_each_person_gets_a_hole_of_their_own(self) -> None:
        """広げた文は 1 つの穴に 1 人ずつ入り、名前は文字として入らない (Being が埋める)。"""
        text = _texts().scene_as_seen(people=(HARU, NATSU), bodies=())

        assert sorted(text.people.items()) == [("person_1", HARU), ("person_2", NATSU)]
        assert "haru" not in text.template

    def test_unidentified_people_each_keep_a_hole(self) -> None:
        """見分けられない人も 1 人ずつの穴に入り、「ここには誰か、誰かがいる。」になる。"""
        text = _texts().scene_as_seen(people=(Unidentified(), Unidentified()), bodies=())

        assert _written(text) == "ここには誰か、誰かがいる。"

    def test_bodies_use_their_own_text(self) -> None:
        """倒れた体は bodies_here の文で「natsuが倒れている。」になる。"""
        text = _texts().scene_as_seen(people=(), bodies=(NATSU,))

        assert _written(text) == "natsuが倒れている。"

    def test_braces_in_joiner_stay_letters(self) -> None:
        """つなぐ言葉に括弧があっても、穴にならず文字のまま並ぶ。"""
        text = _texts(joiner="}{").scene_as_seen(people=(HARU, NATSU), bodies=())

        assert _written(text) == "ここにはharu}{natsuがいる。"

    def test_braces_written_as_letters_in_text_stay_letters(self) -> None:
        """文に文字として書いた括弧 ({{ }}) は、人を並べたあとも穴にならず文字のまま残る。"""
        text = _texts(people_here="{{見える人}}{people}がいる。").scene_as_seen(people=(HARU,), bodies=())

        assert _written(text) == "{見える人}haruがいる。"

    def test_people_and_bodies_follow_in_one_text_with_holes_of_their_own(self) -> None:
        """人も倒れた体もいるとき、people_here の文に bodies_here の文が続き、穴は通し番号で 1 人ずつになる。"""
        text = _texts().scene_as_seen(people=(HARU,), bodies=(NATSU, AKI))

        assert _written(text) == "ここにはharuがいる。natsu、akiが倒れている。"
        assert sorted(text.people.items()) == [("person_1", HARU), ("person_2", NATSU), ("person_3", AKI)]

    def test_listing_no_one_is_refused(self) -> None:
        """人も倒れた体も 1 人も渡さないと NoPeopleToListException を投げる (誰もいないなら文を出さない)。"""
        with pytest.raises(NoPeopleToListException):
            _texts().scene_as_seen(people=(), bodies=())


class TestSurroundingsTextsHoles:
    """SurroundingsTexts が、書ける穴の決まりに合わない文を作るときに断ることを保証する。"""

    @pytest.mark.parametrize(
        "people_here",
        ["ここには誰かがいる。", "{people}と{people}がいる。", "{actor}がいる。", "{people}と{actor}がいる。"],
    )
    def test_people_here_must_write_people_exactly_once(self, people_here: str) -> None:
        """people_here が {people} を書かない・2 回書く・別の穴を書くと PeopleNotWrittenOnceException を投げる。"""
        with pytest.raises(PeopleNotWrittenOnceException):
            _texts(people_here=people_here)

    def test_bodies_here_must_write_people_exactly_once(self) -> None:
        """bodies_here が {people} を書かないと PeopleNotWrittenOnceException を投げる。"""
        with pytest.raises(PeopleNotWrittenOnceException):
            _texts(bodies_here="誰かが倒れている。")

    @pytest.mark.parametrize("field", ["waking", "darkening"])
    def test_notices_cannot_name_people(self, field: str) -> None:
        """waking・darkening に人の穴を書くと PersonInSurroundingsNoticeException を投げる。"""
        with pytest.raises(PersonInSurroundingsNoticeException):
            _texts(**{field: "{people}の目が覚めた。"})

    @pytest.mark.parametrize("joiner", ["", " ", "、\n"])
    def test_joiner_must_be_a_non_blank_single_line(self, joiner: str) -> None:
        """つなぐ言葉が空・空白だけ・複数行だと BlankPeopleJoinerException を投げる。"""
        with pytest.raises(BlankPeopleJoinerException):
            _texts(joiner=joiner)
