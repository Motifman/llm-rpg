from __future__ import annotations

from ai_rpg_world.game_world.domain.action.action_attempt import LivingOnly, UsesBody
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_declaration import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.verb import (
    InteractionDeclaration,
    PerceptionDeclaration,
    SightTextsDeclaration,
    Silent,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import Background, NoTarget
from ai_rpg_world.game_world.domain.value_object import DisplayName, InteractionId
from tests.game_world.domain.declaration.verb.verb_parts import AlwaysHolds, ChangesNothing


def lever_pulled_quietly() -> PerceptionDeclaration:
    return PerceptionDeclaration(
        witness=SightTextsDeclaration(clear=TextWithUnassignedPeople("{actor}がレバーを引いた。")),
        target=NoTarget(),
        sound=Silent(),
        seen_in_dark=False,
        announcement=NoAnnouncement(),
        salience=Background(),
    )


def pull_lever() -> InteractionDeclaration:
    return InteractionDeclaration(
        interaction_id=InteractionId("pull_lever"),
        display_label=DisplayName("レバーを引く"),
        precondition=AlwaysHolds(),
        effect=ChangesNothing(),
        success_text=TextWithUnassignedPeople("レバーを引いた。"),
        shows_on_success=(),
        exertion=UsesBody(),
        actor_requirement=LivingOnly(),
        perceived_as=lever_pulled_quietly(),
        reaches_unseen=False,
        allows_stealth=False,
    )
