from __future__ import annotations

from ai_rpg_world.being.application.people_called_apart import PeopleCalledApart
from ai_rpg_world.being.contract import PersonInText, PersonPlaceholderValue, TextWithPeople, UnidentifiedPerson


def _name_or_appearance(person: PersonPlaceholderValue) -> str:
    if isinstance(person, UnidentifiedPerson):
        return "誰か"
    return person.visible_name or person.appearance


SAYO = PersonInText(handle=3, appearance="前掛けの女", visible_name="サヨ")
SHADOW_A = PersonInText(handle=7, appearance="誰か", visible_name=None)
SHADOW_B = PersonInText(handle=5, appearance="誰か", visible_name=None)


class TestPeopleCalledApart:
    """PeopleCalledApart が、呼び方の重なった人にだけ番号を添え、呼び方から人に戻せることを保証する。"""

    def test_person_with_unique_name_is_called_without_number(self) -> None:
        """呼び方が誰とも重ならない人は、番号を添えずに呼ぶ。"""
        people = PeopleCalledApart(_name_or_appearance, [SAYO, SHADOW_A])

        assert people.name_of(SAYO) == "サヨ"

    def test_people_with_same_name_are_numbered_by_handle_order(self) -> None:
        """呼び方の重なる 2 人は、渡した順によらず、人の印の小さい順に「(1)」「(2)」が付く。"""
        people = PeopleCalledApart(_name_or_appearance, [SHADOW_A, SAYO, SHADOW_B])

        assert (people.name_of(SHADOW_B), people.name_of(SHADOW_A)) == ("誰か (1)", "誰か (2)")

    def test_same_person_given_twice_is_not_numbered(self) -> None:
        """同じ人が候補と理由の両方に出て 2 回渡っても、別の人として番号を付けない。"""
        people = PeopleCalledApart(_name_or_appearance, [SAYO, SAYO])

        assert people.name_of(SAYO) == "サヨ"

    def test_numbered_name_leads_back_to_the_person(self) -> None:
        """番号を添えた呼び方から、その人に戻せる。"""
        people = PeopleCalledApart(_name_or_appearance, [SHADOW_A, SHADOW_B])

        assert people.person_named("誰か (2)") == SHADOW_A

    def test_unknown_name_leads_to_nobody(self) -> None:
        """このターンに出ていない呼び方や、番号を付けずに呼んだ重なる呼び方からは、誰にも戻らない。"""
        people = PeopleCalledApart(_name_or_appearance, [SHADOW_A, SHADOW_B])

        assert (people.person_named("ゲン"), people.person_named("誰か")) == (None, None)

    def test_text_fills_people_with_numbered_names(self) -> None:
        """文の人の穴は番号を添えた呼び方で埋まり、見分けられない人は基本の呼び方の部品の言い方になる。"""
        people = PeopleCalledApart(_name_or_appearance, [SHADOW_A, SHADOW_B])
        text = TextWithPeople(template="{a}が{b}を見ている", people={"a": SHADOW_A, "b": UnidentifiedPerson()})

        assert people.text_of(text) == "誰か (2)が誰かを見ている"
