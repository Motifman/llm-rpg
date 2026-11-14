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
from ai_rpg_world.game_world.domain.whereabouts import Teleported
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
from ai_rpg_world.game_world.domain.world_records.latest_actions import (
    ActionAttemptFailedEvent,
    PersonActedEvent,
)
from ai_rpg_world.game_world.domain.world_records.world_flags import (
    WorldFlagLoweredEvent,
    WorldFlagRaisedEvent,
)


class UntranslatedEventKindError(LookupError):
    pass


def _arrival(event: OccupantEnteredSpotEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    if isinstance(event.origin, Teleported):
        return ()
    origin = design.nouns.spot_of(event.origin)
    return design.built_in_action_perceptions.arrival.seen_at(
        event.spot, event.occupant, {"origin": origin.name}, event.at
    )


def _ran_out(event: ItemRanOutEvent, design: WorldDesign) -> tuple[Stimulus, ...]:
    text = design.nouns.item_spec_of(event.spec_id).lasts.ended_notice()
    return (event.where.read(ItemRanOutNotice(text, event.at)),)


_TRANSLATIONS: dict[type[DomainEvent], Callable[[Any, WorldDesign], tuple[Stimulus, ...]]] = {
    OccupantEnteredSpotEvent: _arrival,
    ItemRanOutEvent: _ran_out,
}

# 刺激を作らない種類。変換をまだ書いていない種類もここに置き、書いたら _TRANSLATIONS へ移す。
NOT_PERCEIVED_EVENT_KINDS: frozenset[type[DomainEvent]] = frozenset(
    {
        ActionAttemptFailedEvent,
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
        PersonActedEvent,
        PersonBecameBusyEvent,
        PersonDamagedEvent,
        PersonDiedEvent,
        PersonFellEvent,
        PersonHealedEvent,
        PersonJoinedGroupEvent,
        PersonLeftGroupEvent,
        PersonNamedEvent,
        PersonOutcomeDecidedEvent,
        PersonRevivedEvent,
        SpotAtmosphereChangedEvent,
        SpotSearchedEvent,
        StatusEffectAddedEvent,
        StatusEffectExpiredEvent,
        TextWrittenEvent,
        TimeOfDayChangedEvent,
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
        translate = _TRANSLATIONS.get(kind)
        if translate is None:
            raise UntranslatedEventKindError(
                f"{kind.__name__} is neither translated into stimuli nor listed as not perceived"
            )
        return translate(event, design)
