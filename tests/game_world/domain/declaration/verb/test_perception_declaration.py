from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.verb import NoFailureWitness
from tests.game_world.domain.declaration.verb.verb_declarations_for_tests import lever_pulled_quietly


class TestPerceptionDeclarationOnFailure:
    """PerceptionDeclaration が、断られたときの目撃の文を書かなければ、見ていた人に何も届けない宣言になることを保証する。"""

    def test_on_failure_left_unwritten_becomes_no_failure_witness(self) -> None:
        """on_failure を書かずに作ると、on_failure は NoFailureWitness になる。"""
        assert lever_pulled_quietly().on_failure == NoFailureWitness()
