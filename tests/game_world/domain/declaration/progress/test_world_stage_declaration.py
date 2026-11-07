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
