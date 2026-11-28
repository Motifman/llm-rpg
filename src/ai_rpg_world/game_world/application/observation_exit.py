from __future__ import annotations

from typing import Final, Protocol, final

from typing_extensions import assert_never

from ai_rpg_world.being.contract import (
    UNKNOWN,
    EnvironmentNotice,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnBodyState,
    PersonInText,
    PersonPlaceholderValue,
    Route,
    SeenOrHeard,
    TextWithPeople,
    UnidentifiedPerson,
)
from ai_rpg_world.game_world.domain.action.action_outcome_for_actor import UnsummarizedAction
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    ClockWording,
    DayAndClockTime,
    DayNightDeclaration,
)
from ai_rpg_world.game_world.domain.lighting import SeesClearly, SeesShapes
from ai_rpg_world.game_world.domain.people import NoVisibleName, PersonRef, TextAboutPeople, Unidentified
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception import Perceived
from ai_rpg_world.game_world.domain.perception.perceived_quality import Felt, NoticedOnWaking, Told
from ai_rpg_world.game_world.domain.sound import HearsClearly, HearsFaintly, HearsMuffled
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId, WorldId


class ObservationReceiver(Protocol):
    def receive(self, person: PersonId, observation: Observation) -> None: ...


@final
class ObservationExit:
    def __init__(
        self, world: WorldId, day_night: DayNightDeclaration, clock: ClockWording, receiver: ObservationReceiver
    ) -> None:
        self._world = world
        self._day_night = day_night
        self._clock = clock
        self._receiver = receiver

    def hand_over(self, perceived: Perceived) -> None:
        self._receiver.receive(
            perceived.perceiver,
            Observation(
                body=text_with_people(perceived.text),
                route=perceived.route(),
                time=observed_time_of(self._day_night.day_and_clock_time_at(perceived.happened_at), self._clock),
                subject_is_self=False,
                subject_name=UNKNOWN,
                source=UNKNOWN,
                place=UNKNOWN,
                addressed_to_self=perceived.addressed_to_perceiver,
                wants_wake=perceived.calls_attention,
                order=OccurrenceOrder(environment=self._world.value, value=perceived.happened_at.value),
            ),
        )


def observed_time_of(time: DayAndClockTime, clock: ClockWording) -> ObservedTime:
    return ObservedTime(display=clock.display(time))


def text_with_people(text: TextWithAssignedPeople) -> TextWithPeople:
    return TextWithPeople(
        template=text.template, people={key: _person_in_text(person) for key, person in text.people.items()}
    )


def action_summary_of(summary: TextAboutPeople | UnsummarizedAction, view: PeopleAsSeen) -> TextWithPeople | None:
    match summary:
        case UnsummarizedAction():
            return None
        case _:
            return text_with_people(summary.seen_by(view))


def _person_in_text(person: PersonRef | Unidentified) -> PersonPlaceholderValue:
    match person:
        case PersonRef():
            return PersonInText(
                handle=person.handle.value,
                appearance=person.appearance.text,
                visible_name=_visible_name(person.visible_name),
            )
        case Unidentified():
            return UnidentifiedPerson()
        case _:
            assert_never(person)


def _visible_name(name: DisplayName | NoVisibleName) -> str | None:
    match name:
        case DisplayName():
            return name.text
        case NoVisibleName():
            return None
        case _:
            assert_never(name)
