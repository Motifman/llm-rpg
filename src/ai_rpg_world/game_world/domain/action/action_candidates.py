from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.action_arguments import ArgumentsNotChosen, ChosenArguments
from ai_rpg_world.game_world.domain.action.built_in_attempts import (
    EnterSectionAttempt,
    GroundItemPickupAttempt,
    GroupDecisionBallotAttempt,
    HoldItemAttempt,
    ItemDropAttempt,
    ItemHandOverAttempt,
    ItemUseAttempt,
    LeaveSectionAttempt,
    PutAwayItemAttempt,
    SpeechAttempt,
    SpotSearchAttempt,
    TendAttempt,
    TravelAttempt,
    WaitAttempt,
)
from ai_rpg_world.game_world.domain.action.interaction_attempts import (
    CarriedItemInteractionAttempt,
    ObjectInteractionAttempt,
    PersonInteractionAttempt,
    SomeoneInTheDark,
)
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, Shout, SpeechContentNotChosen, Whisper
from ai_rpg_world.game_world.domain.action.wait_reason import NoReason
from ai_rpg_world.game_world.domain.declaration.object_and_item import ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import PersonRef
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.surroundings import SeenPerson, VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotSectionId
from ai_rpg_world.game_world.domain.whereabouts.location import OpenArea

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.verb.interaction_declaration import InteractionDeclaration
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class _InView:
    destinations: tuple[SpotDeclaration, ...]
    sections: tuple[SpotSectionDeclaration, ...]
    objects: tuple[ObjectDeclaration, ...]
    ground_items: tuple[ItemInstanceId, ...]
    awake: tuple[PersonId, ...]
    down: tuple[PersonId, ...]
    someone_unidentified: bool
    current_section: SpotSectionId | OpenArea


_NOTHING_IN_VIEW = _InView((), (), (), (), (), (), someone_unidentified=False, current_section=OpenArea())


@final
class ActionCandidates:
    def __init__(
        self, actor: PersonId, seen: VisibleSurroundings | NothingInView, facts: WorldFacts, design: WorldDesign
    ) -> None:
        self._actor = actor
        self._facts = facts
        self._design = design
        self._inventory = facts.inventory(actor)
        self._in_view = _NOTHING_IN_VIEW if isinstance(seen, NothingInView) else _in_view(actor, seen, facts)

    def spot_searches(self) -> tuple[SpotSearchAttempt, ...]:
        return (SpotSearchAttempt(self._actor),)

    def waiting(self) -> tuple[WaitAttempt, ...]:
        return (WaitAttempt(self._actor, NoReason()),)

    def speeches(self) -> tuple[SpeechAttempt, ...]:
        words = SpeechContentNotChosen()
        return (
            SpeechAttempt(self._actor, OrdinaryVoice(), words),
            SpeechAttempt(self._actor, Shout(), words),
            *(SpeechAttempt(self._actor, Whisper(person), words) for person in self._in_view.awake),
        )

    def travels(self) -> tuple[TravelAttempt, ...]:
        return tuple(TravelAttempt(self._actor, destination) for destination in self._in_view.destinations)

    def pickups(self) -> tuple[GroundItemPickupAttempt, ...]:
        return tuple(GroundItemPickupAttempt(self._actor, item, Openly()) for item in self._in_view.ground_items)

    def drops(self) -> tuple[ItemDropAttempt, ...]:
        return tuple(ItemDropAttempt(self._actor, item, Openly()) for item in self._inventory.items())

    def holds(self) -> tuple[HoldItemAttempt, ...]:
        return tuple(HoldItemAttempt(self._actor, item) for item in self._inventory.packed_items())

    def put_aways(self) -> tuple[PutAwayItemAttempt, ...]:
        return tuple(PutAwayItemAttempt(self._actor, item) for item in self._inventory.held_items())

    def item_uses(self) -> tuple[ItemUseAttempt, ...]:
        return tuple(
            ItemUseAttempt(self._actor, item)
            for item in self._inventory.items()
            if self._design.is_usable(self._facts.item(item).spec_id)
        )

    def tends(self) -> tuple[TendAttempt, ...]:
        if not self._facts.rules().tend.allows_tending():
            return ()
        return tuple(TendAttempt(self._actor, person) for person in self._in_view.down)

    def hand_overs(self) -> tuple[ItemHandOverAttempt, ...]:
        return tuple(
            ItemHandOverAttempt(self._actor, person, (item,), Openly())
            for person in self._in_view.awake
            for item in self._inventory.items()
        )

    def section_entries(self) -> tuple[EnterSectionAttempt, ...]:
        current = self._in_view.current_section
        return tuple(
            EnterSectionAttempt(self._actor, self._design.section_access(declared.section_id))
            for declared in self._in_view.sections
            if declared.section_id != current
        )

    def section_exits(self) -> tuple[LeaveSectionAttempt, ...]:
        current = self._in_view.current_section
        if isinstance(current, OpenArea):
            return ()
        return (LeaveSectionAttempt(self._actor, self._design.section_access(current)),)

    def object_interactions(self) -> tuple[ObjectInteractionAttempt, ...]:
        return tuple(
            ObjectInteractionAttempt(self._actor, declared, interaction, _arguments_of(interaction), Openly())
            for declared in self._in_view.objects
            for interaction in self._design.interactions_on_object(declared.object_id)
        )

    def carried_item_interactions(self) -> tuple[CarriedItemInteractionAttempt, ...]:
        return tuple(
            CarriedItemInteractionAttempt(self._actor, item, interaction, _arguments_of(interaction), Openly())
            for item in self._inventory.items()
            for interaction in self._design.interactions_on_item(self._facts.item(item).spec_id)
        )

    def person_interactions(self) -> tuple[PersonInteractionAttempt, ...]:
        return tuple(
            PersonInteractionAttempt(self._actor, person, interaction, _arguments_of(interaction), Openly())
            for person in (*self._in_view.awake, *self._in_view.down)
            for interaction in self._design.person_interactions()
        )

    def ballots(self) -> tuple[GroupDecisionBallotAttempt, ...]:
        people = self._facts.people()
        return tuple(
            GroupDecisionBallotAttempt(self._actor, decision, choice)
            for decision in self._design.nouns.all_group_decisions()
            for choice in self._facts.group_decision(decision).ballot_choices_for(self._actor, people)
        )

    def interactions_in_the_dark(self) -> tuple[PersonInteractionAttempt, ...]:
        if not self._in_view.someone_unidentified:
            return ()
        return tuple(
            PersonInteractionAttempt(self._actor, SomeoneInTheDark(), interaction, _arguments_of(interaction), Openly())
            for interaction in self._design.person_interactions()
            if interaction.reaches_unseen
        )


def _arguments_of(interaction: InteractionDeclaration) -> ChosenArguments | ArgumentsNotChosen:
    return ArgumentsNotChosen() if interaction.arguments else ChosenArguments()


def _in_view(actor: PersonId, seen: VisibleSurroundings, facts: WorldFacts) -> _InView:
    occupant = facts.vitals(actor).occupant_in_world(facts.rules().departed_persons_act)
    people = (*seen.people, *seen.bodies)
    return _InView(
        destinations=tuple(facts.nouns().spot_of(spot) for spot in seen.destinations()),
        sections=seen.sections,
        objects=tuple(shown.declaration for shown in seen.objects),
        ground_items=seen.ground_items,
        awake=_identified(seen.people, facts),
        down=_identified(seen.bodies, facts),
        someone_unidentified=any(not isinstance(shown.person, PersonRef) for shown in people),
        current_section=facts.whereabouts().sections_of_occupants_at(seen.spot).get(occupant, OpenArea()),
    )


def _identified(seen: tuple[SeenPerson, ...], facts: WorldFacts) -> tuple[PersonId, ...]:
    register = facts.people_register()
    by_handle = {register.handle_of(person): person for person in facts.people()}
    return tuple(by_handle[shown.person.handle] for shown in seen if isinstance(shown.person, PersonRef))
