from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.verb import BuiltInActionPerceptions
from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import NotBuiltInActionPerceptionException
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from tests.game_world.support.verb_declarations_for_tests import bell_rung_for_everyone, lever_pulled_quietly

_REFUSED_KINDS = (
    ActionKind.INTERACT_WITH_OBJECT,
    ActionKind.INTERACT_WITH_CARRIED_ITEM,
    ActionKind.INTERACT_WITH_PERSON,
    ActionKind.ENTER_SECTION,
    ActionKind.LEAVE_SECTION,
    ActionKind.ATTACK_MONSTER,
)
_KEPT_KINDS = (
    ActionKind.TRAVEL,
    ActionKind.SPEAK,
    ActionKind.LISTEN,
    ActionKind.WAIT,
    ActionKind.TEND,
    ActionKind.HAND_OVER,
    ActionKind.PICK_UP,
    ActionKind.DROP,
    ActionKind.SEARCH,
    ActionKind.USE_ITEM,
    ActionKind.HOLD,
    ActionKind.PUT_AWAY,
    ActionKind.CAST_BALLOT,
)


class TestBuiltInActionPerceptionsKinds:
    """BuiltInActionPerceptions が、知覚の文を作者の宣言に書かない行為の種類だけを受け取ることを保証する。"""

    @pytest.mark.parametrize(
        "kind",
        _REFUSED_KINDS,
    )
    def test_kind_perceived_through_its_own_declaration_raises(self, kind: ActionKind) -> None:
        """操作の宣言・区画の出入りの宣言が知覚の文を持つ行為か、モンスターへの攻撃を by_kind に書くと、使われない行として NotBuiltInActionPerceptionException を投げる。"""
        with pytest.raises(NotBuiltInActionPerceptionException):
            BuiltInActionPerceptions(by_kind={kind: lever_pulled_quietly()})

    @pytest.mark.parametrize(
        "kind",
        _KEPT_KINDS,
    )
    def test_kind_without_its_own_perception_is_kept(self, kind: ActionKind) -> None:
        """宣言に知覚の欄を持たない行為 (品物を使うことを含む) を by_kind に書くと、断らずにその知覚の宣言を持つ。"""
        perception = lever_pulled_quietly()

        assert BuiltInActionPerceptions(by_kind={kind: perception}).by_kind[kind] == perception

    def test_every_action_kind_is_decided_to_be_refused_or_kept(self) -> None:
        """ActionKind のどの種類も、断る側か受け取る側のどちらか一方のテストに入っている。種類を足したら、表に書けるかをここで決める。"""
        assert sorted(kind.name for kind in _REFUSED_KINDS + _KEPT_KINDS) == sorted(kind.name for kind in ActionKind)

    def test_kinds_left_out_are_not_refused(self) -> None:
        """by_kind に拾うことだけを書いても断らない。表に足りない行為は、世界を組み立てるときに照らし合わせる。"""
        perceptions = BuiltInActionPerceptions(by_kind={ActionKind.PICK_UP: lever_pulled_quietly()})

        assert set(perceptions.by_kind) == {ActionKind.PICK_UP}


class TestBuiltInActionPerceptionsKeepsItsOwnTable:
    """BuiltInActionPerceptions が、作った後に渡した表を書き換えられても中身を変えないことを保証する。"""

    def test_changing_the_passed_mapping_does_not_change_the_declaration(self) -> None:
        """作るときに渡した dict の拾うことの行を後から差し替えても、宣言の拾うことの知覚は作ったときのまま。"""
        quiet = lever_pulled_quietly()
        table = {ActionKind.PICK_UP: quiet}
        perceptions = BuiltInActionPerceptions(by_kind=table)

        table[ActionKind.PICK_UP] = bell_rung_for_everyone()

        assert perceptions.by_kind[ActionKind.PICK_UP] == quiet
