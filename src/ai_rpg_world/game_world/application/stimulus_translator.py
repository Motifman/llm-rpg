from __future__ import annotations

from collections.abc import Callable
from typing import Any, final

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.objects_and_items.ground_items import (
    GroundItemPlacedEvent,
    GroundItemTakenEvent,
)
from ai_rpg_world.game_world.domain.objects_and_items.item import (
    ItemCameIntoWorldEvent,
    ItemLeftWorldEvent,
    ItemRanOutEvent,
    ItemStateChangedEvent,
)
from ai_rpg_world.game_world.domain.objects_and_items.object_state import (
    ObjectRevealedEvent,
    ObjectStateChangedEvent,
    TextWrittenEvent,
)
from ai_rpg_world.game_world.domain.objects_and_items.person_inventory import (
    GoldEarnedEvent,
    GoldPaidEvent,
    ItemGivenUpEvent,
    ItemHeldEvent,
    ItemPutAwayEvent,
    ItemReceivedEvent,
)
from ai_rpg_world.game_world.domain.objects_and_items.spot_search_progress import (
    DiscoverableFoundEvent,
    SpotSearchedEvent,
)
from ai_rpg_world.game_world.domain.people.people_register import (
    PersonNamedEvent,
)
from ai_rpg_world.game_world.domain.perception import ItemRanOutNotice, Stimulus
from ai_rpg_world.game_world.domain.person.group_membership import (
    PersonJoinedGroupEvent,
    PersonLeftGroupEvent,
)
from ai_rpg_world.game_world.domain.person.person_outcomes import (
    PersonOutcomeDecidedEvent,
)
from ai_rpg_world.game_world.domain.person.person_vitals_events import (
    FatigueLevelChangedEvent,
    HungerLevelChangedEvent,
    PersonBecameBusyEvent,
    PersonDamagedEvent,
    PersonDiedEvent,
    PersonFellEvent,
    PersonHealedEvent,
    PersonRevivedEvent,
    StatusEffectAddedEvent,
    StatusEffectExpiredEvent,
)
from ai_rpg_world.game_world.domain.whereabouts.passage_state_events import (
    PassageRemovedEvent,
    PassageRevealedEvent,
    PassageStateChangedEvent,
)
from ai_rpg_world.game_world.domain.whereabouts.spot_atmosphere_events import (
    SpotAtmosphereChangedEvent,
)
from ai_rpg_world.game_world.domain.whereabouts.whereabouts_events import (
    OccupantEnteredSectionEvent,
    OccupantEnteredSpotEvent,
    OccupantLeftSectionEvent,
    OccupantLeftSpotEvent,
    OccupantPlacedEvent,
    OccupantRemovedEvent,
    OccupantTeleportedEvent,
    TravelBlockedEvent,
    TravelCancelledEvent,
    TravelStartedEvent,
)
from ai_rpg_world.game_world.domain.world_progress.group_decision import (
    BallotCastEvent,
    ChoiceWithdrawnEvent,
    GroupDecisionReachedEvent,
    GroupDecisionStartedEvent,
    GroupDecisionUnresolvedEvent,
    VoterWithdrawnEvent,
)
from ai_rpg_world.game_world.domain.world_progress.weather import (
    WeatherChangedEvent,
)
from ai_rpg_world.game_world.domain.world_progress.world_clock import (
    TimeOfDayChangedEvent,
    WorldTickAdvancedEvent,
)
from ai_rpg_world.game_world.domain.world_progress.world_ending import (
    WorldEndedEvent,
)
from ai_rpg_world.game_world.domain.world_progress.world_stage import (
    WorldStageChangedEvent,
)
from ai_rpg_world.game_world.domain.world_records.joint_action_progress import (
    JointActionCompletedEvent,
    JointActionSettlement,
    JointActionTimedOutEvent,
)
from ai_rpg_world.game_world.domain.world_records.latest_actions import (
    ActionAttemptFailedEvent,
    PersonActedEvent,
)
from ai_rpg_world.game_world.domain.world_records.scenario_progress import (
    HappeningFiredEvent,
    ReactionFiredEvent,
)
from ai_rpg_world.game_world.domain.world_records.world_flags import (
    WorldFlagLoweredEvent,
    WorldFlagRaisedEvent,
)


class UntranslatedEventKindError(LookupError):
    pass


def _arrival(event: OccupantEnteredSpotEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    return design.built_in_action_perceptions.arrival_seen_at(
        event.spot, event.occupant, event.origin, design.nouns, event.at
    )


def _acted(event: PersonActedEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    return event.attempt.witnessed_in(design, event.item_specs).stimuli_at(
        event.at_spot, event.actor_as, event.present, event.at
    )


def _failed(event: ActionAttemptFailedEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    return event.refusal.stimuli_at(design, event.item_specs, event.at_spot, event.actor_as, event.at)


def _happened(event: HappeningFiredEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    return design.happening(event.happening_id).stimuli_when_fired(
        event.refusal, event.audience, event.present, event.at
    )


def _joint_completed(event: JointActionCompletedEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    return design.joint_action(event.joint_id).stimuli_when_settled(
        JointActionSettlement.COMPLETED, event.refusal, event.audience, event.present, event.at
    )


def _joint_timed_out(event: JointActionTimedOutEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    return design.joint_action(event.joint_id).stimuli_when_settled(
        JointActionSettlement.TIMED_OUT, event.refusal, event.audience, event.present, event.at
    )


def _outcome_decided(event: PersonOutcomeDecidedEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    return event.outcome.announced_to(event.person, event.at)


def _time_of_day_changed(event: TimeOfDayChangedEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    return design.day_night.phase_named(event.after).stimuli_when_entered(event.audience, event.at)


def _ran_out(event: ItemRanOutEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    text = design.nouns.item_spec_of(event.spec_id).lasts.ended_notice()
    return (event.where.read(ItemRanOutNotice(text, event.at)),)


_TRANSLATIONS: dict[type[DomainEvent], Callable[[Any, WorldDesign], tuple[Stimulus, ...]]] = {
    OccupantEnteredSpotEvent: _arrival,
    ItemRanOutEvent: _ran_out,
    PersonActedEvent: _acted,
    ActionAttemptFailedEvent: _failed,
    HappeningFiredEvent: _happened,
    JointActionCompletedEvent: _joint_completed,
    JointActionTimedOutEvent: _joint_timed_out,
    PersonOutcomeDecidedEvent: _outcome_decided,
    TimeOfDayChangedEvent: _time_of_day_changed,
}

NOT_PERCEIVED_EVENT_KINDS: frozenset[type[DomainEvent]] = frozenset(
    {
        BallotCastEvent,
        ChoiceWithdrawnEvent,
        DiscoverableFoundEvent,
        FatigueLevelChangedEvent,
        GoldEarnedEvent,
        GoldPaidEvent,
        GroundItemPlacedEvent,
        GroundItemTakenEvent,
        GroupDecisionReachedEvent,
        GroupDecisionStartedEvent,
        GroupDecisionUnresolvedEvent,
        HungerLevelChangedEvent,
        ItemCameIntoWorldEvent,
        ItemGivenUpEvent,
        ItemHeldEvent,
        ItemLeftWorldEvent,
        ItemPutAwayEvent,
        ItemReceivedEvent,
        ItemStateChangedEvent,
        ObjectRevealedEvent,
        ObjectStateChangedEvent,
        OccupantEnteredSectionEvent,
        OccupantLeftSectionEvent,
        OccupantLeftSpotEvent,
        OccupantPlacedEvent,
        OccupantRemovedEvent,
        OccupantTeleportedEvent,
        PassageRemovedEvent,
        PassageRevealedEvent,
        PassageStateChangedEvent,
        PersonBecameBusyEvent,
        PersonDamagedEvent,
        PersonDiedEvent,
        PersonFellEvent,
        PersonHealedEvent,
        PersonJoinedGroupEvent,
        PersonLeftGroupEvent,
        PersonNamedEvent,
        PersonRevivedEvent,
        ReactionFiredEvent,
        SpotAtmosphereChangedEvent,
        SpotSearchedEvent,
        StatusEffectAddedEvent,
        StatusEffectExpiredEvent,
        TextWrittenEvent,
        TravelBlockedEvent,
        TravelCancelledEvent,
        TravelStartedEvent,
        VoterWithdrawnEvent,
        WeatherChangedEvent,
        WorldEndedEvent,
        WorldFlagLoweredEvent,
        WorldFlagRaisedEvent,
        WorldStageChangedEvent,
        WorldTickAdvancedEvent,
    }
)


@final
class StimulusTranslator:
    @classmethod
    def translated_kinds(cls) -> frozenset[type[DomainEvent]]:
        return frozenset(_TRANSLATIONS)

    def stimuli_of(self, event: DomainEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
        kind = type(event)
        if kind in NOT_PERCEIVED_EVENT_KINDS:
            return ()
        if kind not in _TRANSLATIONS:
            raise UntranslatedEventKindError(
                f"{kind.__name__} is neither translated into stimuli nor listed as not perceived"
            )
        return _TRANSLATIONS[kind](event, design)
