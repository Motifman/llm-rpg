from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.acquaintance import (
    Acquaintance,
    AcquaintanceInvalid,
    HowKnown,
)


class TestAcquaintance:
    """Acquaintance が、相手をどう知ったかと、会った回数と時期を Being のターン数で持つことを保証する。"""

    def test_first_meeting_counts_one_and_fixes_both_turns(self) -> None:
        """会って初めて知った記録は、知り方が「会った」、会った回数が 1 で、知ったターン・初めて会ったターン・最後に会ったターンが同じになる。"""
        met = Acquaintance.first_meeting(environment_name="島", name="ノア", turn=3)

        assert met.how_known is HowKnown.MET
        assert (met.known_since_turn, met.met_count, met.first_met_turn, met.last_met_turn) == (3, 1, 3, 3)
        assert met.is_first_meeting

    def test_introduction_is_known_but_not_met(self) -> None:
        """紹介された記録は、知り方が「紹介された」で関係の注記を持ち、会った回数は 0、会ったターンは無い。"""
        known = Acquaintance.introduced(
            environment_name="山村", name="ノア", turn=0, relation_note="あなたと同じ側"
        )

        assert known.how_known is HowKnown.INTRODUCED
        assert known.relation_note == "あなたと同じ側"
        assert (known.met_count, known.first_met_turn, known.last_met_turn) == (0, None, None)
        assert not known.is_first_meeting

    def test_meeting_someone_introduced_keeps_how_known(self) -> None:
        """紹介された相手に初めて会うと、知り方と注記は変わらず、会った回数 1 と会ったターンが付く。"""
        known = Acquaintance.introduced(environment_name="山村", name="ノア", turn=0)

        met = known.met_at(turn=4)

        assert met.how_known is HowKnown.INTRODUCED
        assert (met.met_count, met.first_met_turn, met.last_met_turn) == (1, 4, 4)
        assert met.is_first_meeting

    def test_meeting_again_advances_only_the_last_turn(self) -> None:
        """もう一度会うと回数が増え、最後に会ったターンだけが進み、初めて会ったターンは変わらない。"""
        met = Acquaintance.first_meeting(environment_name="島", name="ノア", turn=3)

        again = met.met_at(turn=7)

        assert (again.met_count, again.first_met_turn, again.last_met_turn) == (2, 3, 7)
        assert not again.is_first_meeting

    def test_meeting_in_an_earlier_turn_is_rejected(self) -> None:
        """最後に会ったターン、または知ったターンより前のターンで会おうとすると AcquaintanceInvalid を投げる。"""
        met = Acquaintance.first_meeting(environment_name="島", name="ノア", turn=7)
        known = Acquaintance.introduced(environment_name="島", name="カイ", turn=5)

        with pytest.raises(AcquaintanceInvalid):
            met.met_at(turn=6)
        with pytest.raises(AcquaintanceInvalid):
            known.met_at(turn=4)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"environment_name": " ", "name": "ノア", "turn": 0},
            {"environment_name": "島", "name": "", "turn": 0},
            {"environment_name": "島", "name": "ノア", "turn": -1},
            {"environment_name": "島", "name": "ノア", "turn": True},
        ],
    )
    def test_blank_names_or_invalid_turn_are_rejected(self, kwargs: dict) -> None:
        """環境の名前や相手の名前が空、またはターンが負か整数でないとき AcquaintanceInvalid を投げる。"""
        with pytest.raises(AcquaintanceInvalid):
            Acquaintance.first_meeting(**kwargs)

    @pytest.mark.parametrize(
        "fields",
        [
            {"how_known": HowKnown.MET, "met_count": 0, "first_met_turn": None, "last_met_turn": None},
            {"how_known": HowKnown.INTRODUCED, "met_count": 0, "first_met_turn": 2, "last_met_turn": 2},
            {"how_known": HowKnown.INTRODUCED, "met_count": 2, "first_met_turn": None, "last_met_turn": None},
            {"how_known": HowKnown.INTRODUCED, "met_count": 2, "first_met_turn": 5, "last_met_turn": 4},
            {"how_known": HowKnown.INTRODUCED, "met_count": 1, "first_met_turn": 1, "last_met_turn": 1},
            {"how_known": HowKnown.MET, "met_count": 1, "first_met_turn": 3, "last_met_turn": 3},
            {"how_known": HowKnown.INTRODUCED, "met_count": -1, "first_met_turn": None, "last_met_turn": None},
            {"how_known": HowKnown.INTRODUCED, "met_count": 0, "first_met_turn": None, "last_met_turn": None, "relation_note": ""},
        ],
        ids=[
            "met_without_meeting",
            "turns_without_meeting",
            "meetings_without_turns",
            "last_before_first",
            "met_before_known",
            "met_after_known_for_met",
            "negative_count",
            "blank_note",
        ],
    )
    def test_inconsistent_records_are_rejected(self, fields: dict) -> None:
        """回数と会ったターンが食い違う、知る前に会っている、会って知ったのに知ったターンと初めて会ったターンが違う、注記が空、のどれでも作れない。"""
        with pytest.raises(AcquaintanceInvalid):
            Acquaintance(
                environment_name="島", name="ノア", known_since_turn=2,
                **{"name_learned_turn": 2, **fields},
            )


class TestKnowingTheName:
    """Acquaintance が、会ったことと名前を知っていることを分けて持つことを保証する (#1581)。"""

    def test_introduction_knows_the_name_from_the_start(self) -> None:
        """紹介された相手は、紹介されたターンから名前を知っている。"""
        known = Acquaintance.introduced(environment_name="山村", name="ノア", turn=2)

        assert known.knows_name
        assert known.name_learned_turn == 2

    def test_meeting_a_stranger_does_not_teach_the_name(self) -> None:
        """名前を知らずに会った相手は、会った記録はあるが名前を知らない。"""
        met = Acquaintance.first_meeting(
            environment_name="山村", name="ノア", turn=3, knows_name=False
        )

        assert met.met_count == 1
        assert not met.knows_name
        assert met.name_learned_turn is None

    def test_learning_the_name_keeps_the_meeting_and_fixes_the_turn(self) -> None:
        """名前を知ると、知ったターンが付き、会った回数と知り方は変わらない。"""
        met = Acquaintance.first_meeting(
            environment_name="山村", name="ノア", turn=3, knows_name=False
        ).met_at(turn=5)

        named = met.learned_name(turn=6)

        assert named.knows_name
        assert named.name_learned_turn == 6
        assert (named.how_known, named.met_count, named.last_met_turn) == (HowKnown.MET, 2, 5)

    def test_learning_a_known_name_again_keeps_the_first_turn(self) -> None:
        """すでに名前を知っている相手の名前をもう一度聞いても、知ったターンは変わらない。"""
        known = Acquaintance.introduced(environment_name="山村", name="ノア", turn=1)

        assert known.learned_name(turn=8).name_learned_turn == 1

    def test_meeting_again_does_not_teach_the_name(self) -> None:
        """名前を知らない相手と何度会っても、名前は知らないまま。"""
        met = Acquaintance.first_meeting(
            environment_name="山村", name="ノア", turn=3, knows_name=False
        )

        assert not met.met_at(turn=9).knows_name

    @pytest.mark.parametrize(
        "fields",
        [
            {"how_known": HowKnown.INTRODUCED, "met_count": 0, "name_learned_turn": None},
            {"how_known": HowKnown.INTRODUCED, "met_count": 0, "name_learned_turn": 4},
            {"how_known": HowKnown.MET, "met_count": 1, "first_met_turn": 2, "last_met_turn": 2, "name_learned_turn": 1},
            {"how_known": HowKnown.MET, "met_count": 1, "first_met_turn": 2, "last_met_turn": 2, "name_learned_turn": True},
        ],
        ids=["introduced_without_name", "introduced_name_later", "name_before_meeting", "bool_turn"],
    )
    def test_inconsistent_name_turns_are_rejected(self, fields: dict) -> None:
        """紹介なのに名前を知らない・紹介と違うターンに知った、会う前に名前を知った、ターンが整数でない、のどれでも作れない。"""
        with pytest.raises(AcquaintanceInvalid):
            Acquaintance(
                environment_name="島", name="ノア", known_since_turn=2,
                **{"name_learned_turn": 2, **fields},
            )
