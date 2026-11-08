from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired, ReactionFired
from ai_rpg_world.game_world.domain.declaration.verb import HappeningDeclaration, NoNotice, ReactionDeclaration
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from tests.game_world.domain.declaration.verb.verb_parts import AlwaysHolds, ChangesNothing


class TestHappeningDeclarationAsTrigger:
    """HappeningDeclaration が、出来事が起きたきっかけにそのまま入ることを保証する。"""

    def test_fired_trigger_answers_the_declared_happening_id(self) -> None:
        """HappeningFired に宣言を包むと、きっかけから宣言の happening_id が読める。"""
        happening = HappeningDeclaration(
            happening_id=HappeningId("lights_go_out"),
            condition=AlwaysHolds(),
            effect=ChangesNothing(),
            once=True,
            notice=NoNotice(),
        )

        assert HappeningFired(happening=happening).happening.happening_id == HappeningId("lights_go_out")


class TestReactionDeclarationAsTrigger:
    """ReactionDeclaration が、反応が起きたきっかけにそのまま入ることを保証する。"""

    def test_fired_trigger_answers_the_declared_reaction_id(self) -> None:
        """ReactionFired に宣言を包むと、きっかけから宣言の reaction_id が読める。"""
        reaction = ReactionDeclaration(
            reaction_id=ReactionId("door_follows_lever"),
            condition=AlwaysHolds(),
            when_becomes_true=ChangesNothing(),
            when_becomes_false=ChangesNothing(),
        )

        assert ReactionFired(reaction=reaction).reaction.reaction_id == ReactionId("door_follows_lever")
