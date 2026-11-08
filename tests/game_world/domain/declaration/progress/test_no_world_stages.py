from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
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
