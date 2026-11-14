from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.progress import AllActionsAllowed, WorldStageDeclaration
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, InteractionId, WorldStageId


def _stage(allowed_actions: frozenset[ActionKind | InteractionId] | AllActionsAllowed) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId("night"),
        name=DisplayName("夜"),
        description=DescriptionText("人狼が動く時間"),
        allowed_actions=allowed_actions,
    )


class TestAllowedActions:
    """WorldStageDeclaration.allowed_actions が、行為の種類と操作の名前の両方で許す行為を表せることを保証する。"""

    def test_mixes_action_kinds_and_interaction_ids(self) -> None:
        """行為の種類 (ActionKind) と操作の名前 (InteractionId) を混ぜた集合を持てる。"""
        allowed = frozenset({ActionKind.SPEAK, InteractionId("bite")})

        assert _stage(allowed).allowed_actions == allowed


class TestWorldStageDeclarationAsKey:
    """WorldStageDeclaration が、条件・効果で比べたり集合に入れたりできることを保証する。"""

    def test_declarations_with_same_fields_are_equal_and_hash_alike(self) -> None:
        """同じ欄を持つ 2 つの WorldStageDeclaration は等しく、集合では 1 つにまとまる。"""
        first = _stage(frozenset({ActionKind.CAST_BALLOT}))
        second = _stage(frozenset({ActionKind.CAST_BALLOT}))

        assert first == second
        assert len({first, second}) == 1


class TestAllows:
    """WorldStageDeclaration.allows / allows_interaction が、組み込みの行為は ActionKind、作者の操作は InteractionId で許可を照らすことを保証する。"""

    def test_allows_action_kind_listed_in_allowed_actions(self) -> None:
        """allowed_actions に SPEAK があれば、allows(SPEAK) は真、allows(TRAVEL) は偽を返す。"""
        stage = _stage(frozenset({ActionKind.SPEAK}))

        assert stage.allows(ActionKind.SPEAK)
        assert not stage.allows(ActionKind.TRAVEL)

    def test_allows_interaction_listed_in_allowed_actions(self) -> None:
        """allowed_actions に InteractionId("bite") があれば、allows_interaction("bite") は真、("vote") は偽を返す。"""
        stage = _stage(frozenset({InteractionId("bite")}))

        assert stage.allows_interaction(InteractionId("bite"))
        assert not stage.allows_interaction(InteractionId("vote"))

    def test_interaction_kind_does_not_allow_any_interaction_by_itself(self) -> None:
        """allowed_actions に INTERACT_WITH_PERSON があっても、作者の操作は InteractionId で照らすので allows_interaction は偽を返す。"""
        stage = _stage(frozenset({ActionKind.INTERACT_WITH_PERSON}))

        assert not stage.allows_interaction(InteractionId("bite"))

    def test_all_actions_allowed_allows_every_kind_and_interaction(self) -> None:
        """allowed_actions が AllActionsAllowed なら、どの ActionKind も InteractionId も許す。"""
        stage = _stage(AllActionsAllowed())

        assert all(stage.allows(kind) for kind in ActionKind)
        assert stage.allows_interaction(InteractionId("bite"))


class TestWorldStageDeclarationIsDeclared:
    """WorldStageDeclaration.is_declared が、段階を宣言した世界であることを答えることを保証する。"""

    def test_is_declared(self) -> None:
        """段階の宣言は、段階が宣言されているかを問われると、宣言されていると答える。"""
        assert _stage(AllActionsAllowed()).is_declared()
