from __future__ import annotations

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired, ReactionFired
from ai_rpg_world.game_world.domain.declaration.verb import HappeningDeclaration, NoNotice, ReactionDeclaration
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from tests.game_world.support.verb_declarations_for_tests import as_fired_happening, as_fired_reaction
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds, ChangesNothing


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

        trigger = HappeningFired(happening=as_fired_happening(happening))

        assert trigger.happening.happening_id == HappeningId("lights_go_out")


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

        trigger = ReactionFired(reaction=as_fired_reaction(reaction))

        assert trigger.reaction.reaction_id == ReactionId("door_follows_lever")
