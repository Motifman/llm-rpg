from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.world_design_exception import BlankDeclaredNameException
from ai_rpg_world.game_world.domain.value_object import (
    FlagId,
    GroupDecisionId,
    GroupId,
    GroupingId,
    InteractionId,
    ItemSpecId,
    ObjectId,
    OutcomeId,
    PassageId,
    PassageStateName,
    PersonId,
    SpotId,
    SpotSectionId,
    StateKeyId,
    WorldStageId,
)
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName

DECLARED_ID_TYPES = [
    FlagId,
    ObjectId,
    ItemSpecId,
    PassageId,
    SpotSectionId,
    GroupId,
    GroupingId,
    PersonId,
    WorldStageId,
    GroupDecisionId,
    OutcomeId,
    StateKeyId,
    PassageStateName,
    InteractionId,
    ArgumentName,
]


@pytest.mark.parametrize("id_type", DECLARED_ID_TYPES, ids=lambda t: t.__name__)
class TestDeclaredIdHoldsName:
    """名詞の宣言を指す ID の型が、シナリオの宣言した名前を持ち、空の名前と文字列でない値を断ることを保証する。"""

    def test_declared_name_is_kept_as_is(self, id_type: type) -> None:
        """宣言の名前 "lift_lever" を渡すと、value にそのまま持つ。"""
        assert id_type("lift_lever").value == "lift_lever"

    def test_same_name_means_the_same_declaration(self, id_type: type) -> None:
        """同じ名前の ID は等しく、辞書のキーとして同じ宣言を指す。"""
        assert id_type("lever") == id_type("lever")
        assert {id_type("lever"): 1}[id_type("lever")] == 1

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_name_raises_domain_exception(self, id_type: type, raw: str) -> None:
        """空の名前や空白だけの名前を渡すと BlankDeclaredNameException を投げる。"""
        with pytest.raises(BlankDeclaredNameException):
            id_type(raw)

    @pytest.mark.parametrize("raw", [1, None])
    def test_non_string_raises_domain_exception(self, id_type: type, raw: object) -> None:
        """文字列でない値 (古い世界の連番の int など) を渡すと BlankDeclaredNameException を投げる。"""
        with pytest.raises(BlankDeclaredNameException):
            id_type(raw)

    def test_blank_name_message_names_the_id_type(self, id_type: type) -> None:
        """空の名前を断るとき、どの種類の ID で断ったかがメッセージに出る。"""
        with pytest.raises(BlankDeclaredNameException, match=id_type.__name__):
            id_type("")


class TestDeclaredIdKindsAreDistinct:
    """名前が同じでも、指す名詞の種類が違う ID は別のものとして扱われることを保証する。"""

    def test_object_and_flag_with_the_same_name_are_not_equal(self) -> None:
        """ObjectId("lever") と FlagId("lever") は等しくない。"""
        assert ObjectId("lever") != FlagId("lever")

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            (left, right)
            for left in [*DECLARED_ID_TYPES, SpotId]
            for right in [*DECLARED_ID_TYPES, SpotId]
            if left is not right
        ],
        ids=lambda t: t.__name__,
    )
    def test_any_two_kinds_with_the_same_name_are_not_equal(self, left: type, right: type) -> None:
        """どの 2 種類の ID (SpotId を含む) も、同じ名前 "lever" を持っていても等しくなく、辞書のキーとしても別になる。"""
        assert left("lever") != right("lever")
        assert len({left("lever"), right("lever")}) == 2
