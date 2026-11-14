from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.exception.condition_exception import NotDeclaredInThisWorldException
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId


def _nouns() -> DeclaredNouns:
    return DeclaredNouns(
        flags=(),
        spots=(),
        passages=(),
        objects=(),
        item_specs=(),
        groupings=(),
        groups=(),
        characters=(),
        world_stages=(),
        group_decisions=(),
        sections=(),
        outcomes=(),
    )


class TestNoWorldStages:
    """段階を宣言しない世界の NoWorldStages が、段階の宣言と同じ問いに「どの行為も許す」と答えることを保証する。"""

    @pytest.mark.parametrize("kind", list(ActionKind), ids=lambda kind: kind.name)
    def test_allows_every_built_in_kind(self, kind: ActionKind) -> None:
        """どの ActionKind を問われても許す。"""
        assert NoWorldStages().allows(kind)

    def test_allows_every_interaction(self) -> None:
        """作者が宣言したどの操作の InteractionId を問われても許す。"""
        assert NoWorldStages().allows_interaction(InteractionId("pull_lever"))

    def test_declaration_in_answers_itself(self) -> None:
        """declaration_in は、名詞の宣言に段階が 1 つも無くても、自分自身を返す。"""
        assert NoWorldStages().declaration_in(_nouns()) == NoWorldStages()

    def test_current_raises_not_declared(self) -> None:
        """いまの段階を問われると、「段階を宣言していない」という文面の NotDeclaredInThisWorldException を投げる。"""
        with pytest.raises(NotDeclaredInThisWorldException, match="^this world declares no world stages$"):
            NoWorldStages().current()

    def test_entered_at_raises_not_declared(self) -> None:
        """いまの段階に入った tick を問われると、「段階を宣言していない」という文面の NotDeclaredInThisWorldException を投げる。"""
        with pytest.raises(NotDeclaredInThisWorldException, match="^this world declares no world stages$"):
            NoWorldStages().entered_at()

    def test_is_not_declared(self) -> None:
        """段階が宣言されているかを問われると、宣言されていないと答える。"""
        assert not NoWorldStages().is_declared()
