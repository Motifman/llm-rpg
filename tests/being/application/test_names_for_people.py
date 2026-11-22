"""環境が人の穴で渡した文を、Being が呼び名で埋める基本の決まりを保証する (D1928)。"""

from __future__ import annotations

from ai_rpg_world.being.application.names_for_people import name_for, text_naming_people
from ai_rpg_world.being.contract import PersonInText, TextWithPeople, UnidentifiedPerson

_SAYO = PersonInText(handle=2, appearance="小柄な女", visible_name="サヨ")
_STRANGER = PersonInText(handle=5, appearance="背の高い男", visible_name=None)


class TestNameFor:
    """1 人の呼び名を、見えている名前・見た目・見分けられない、の順に決めることを保証する。"""

    def test_visible_name_is_used_when_the_name_is_seen(self) -> None:
        """名前が見えている人は、見た目ではなく名前で呼ぶ。"""
        assert name_for(_SAYO) == "サヨ"

    def test_appearance_is_used_when_no_name_is_seen(self) -> None:
        """名前が見えない人は、見た目で呼ぶ。"""
        assert name_for(_STRANGER) == "背の高い男"

    def test_unidentified_person_is_called_someone(self) -> None:
        """見分けられない人は「誰か」と呼ぶ。"""
        assert name_for(UnidentifiedPerson()) == "誰か"


class TestTextNamingPeople:
    """文の人の穴を、それぞれの人の呼び名で埋めることを保証する。"""

    def test_every_placeholder_is_filled_with_its_person(self) -> None:
        """穴が複数あっても、穴ごとの人の呼び名で埋まる。"""
        text = TextWithPeople(
            template="ここには{person_1}、{person_2}がいる。{person_3}が倒れている。",
            people={"person_1": _SAYO, "person_2": _STRANGER, "person_3": UnidentifiedPerson()},
        )

        assert text_naming_people(text) == "ここにはサヨ、背の高い男がいる。誰かが倒れている。"

    def test_literal_braces_stay_as_braces(self) -> None:
        """文の中の {{ }} は、人の穴ではなく括弧の文字として残る。"""
        text = TextWithPeople(template="{{札}}の前に{person_1}がいる。", people={"person_1": _SAYO})

        assert text_naming_people(text) == "{札}の前にサヨがいる。"
