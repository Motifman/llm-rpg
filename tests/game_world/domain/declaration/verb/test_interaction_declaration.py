from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.verb import DefaultDuration
from tests.game_world.domain.declaration.verb.verb_declarations_for_tests import pull_lever


class TestInteractionDeclarationDuration:
    """InteractionDeclaration が、行っているあいだを書かなければ世界の決まりの既定に任せることを保証する。"""

    def test_duration_left_unwritten_becomes_default_duration(self) -> None:
        """duration を書かずに作ると、duration は DefaultDuration になる。"""
        assert pull_lever().duration == DefaultDuration()
