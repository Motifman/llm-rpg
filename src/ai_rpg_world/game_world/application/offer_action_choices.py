from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import ActionChoices
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.list_available_actions import ListAvailableActions
from ai_rpg_world.game_world.application.look_around import SurroundingsOf
from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses, perceiver_of
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.choice_wording import ChoiceWording
from ai_rpg_world.game_world.domain.action.offers_of_one_turn import OffersOfOneTurn
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class OfferActionChoicesCommand:
    person: PersonId


@final
class OfferActionChoices:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._design = design
        self._list = ListAvailableActions(scope, design)

    def __call__(self, command: OfferActionChoicesCommand) -> ActionChoices:
        return self._scope.run(lambda session: self._offer(session, command.person))

    def _offer(self, session: WorldSession, person: PersonId) -> ActionChoices:
        facts = session.facts()
        seen = VisibleSurroundings.seen_by(perceiver_of(facts, person), SurroundingsOf(person, facts, self._design))
        people = WorldPerceptionSenses(facts).view_for(person)
        wording = ChoiceWording.seeing(person, self._design, facts, people, seen)
        return OffersOfOneTurn.of(self._list.available_in(session, person), wording).as_action_choices()
