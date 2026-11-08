from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.exception.world_progress_exception import (
    AbstainNotAllowedException,
    BallotAlreadyCastException,
    ChoiceNotInDecisionException,
    GroupDecisionAlreadyOpenException,
    GroupDecisionNotOpenException,
    NoChoicesGivenException,
    NoVotersGivenException,
    VoterNotInDecisionException,
)
from ai_rpg_world.game_world.domain.value_object import GroupDecisionId, PersonId


@final
@dataclass(frozen=True)
class VoteFor:
    person: PersonId


@final
@dataclass(frozen=True)
class Abstain:
    pass


@final
@dataclass(frozen=True)
class Ballot:
    voter: PersonId
    choice: VoteFor | Abstain


@final
@dataclass(frozen=True)
class GroupDecisionStartedEvent(DomainEvent):
    decision_id: GroupDecisionId
    voters: frozenset[PersonId]
    choices: frozenset[PersonId]


@final
@dataclass(frozen=True)
class BallotCastEvent(DomainEvent):
    decision_id: GroupDecisionId
    voter: PersonId
    choice: VoteFor | Abstain


@final
@dataclass(frozen=True)
class VoterWithdrawnEvent(DomainEvent):
    decision_id: GroupDecisionId
    voter: PersonId


@final
@dataclass(frozen=True)
class ChoiceWithdrawnEvent(DomainEvent):
    decision_id: GroupDecisionId
    choice: PersonId
    returned_to: frozenset[PersonId]


@final
@dataclass(frozen=True)
class GroupDecisionReachedEvent(DomainEvent):
    decision_id: GroupDecisionId
    chosen: PersonId
    ballots: frozenset[Ballot]


@final
@dataclass(frozen=True)
class GroupDecisionUnresolvedEvent(DomainEvent):
    decision_id: GroupDecisionId
    ballots: frozenset[Ballot]


GroupDecisionEvent = (
    GroupDecisionStartedEvent
    | BallotCastEvent
    | VoterWithdrawnEvent
    | ChoiceWithdrawnEvent
    | GroupDecisionReachedEvent
    | GroupDecisionUnresolvedEvent
)


class GroupDecision(AggregateRoot[GroupDecisionEvent]):
    def __init__(self, declaration: GroupDecisionDeclaration) -> None:
        super().__init__()
        self._decision_id = declaration.decision_id
        self._abstain_allowed = declaration.abstain_allowed
        self._open = False
        self._voters: set[PersonId] = set()
        self._choices: set[PersonId] = set()
        self._ballots: dict[PersonId, VoteFor | Abstain] = {}

    @property
    def decision_id(self) -> GroupDecisionId:
        return self._decision_id

    def start(self, voters: frozenset[PersonId], choices: frozenset[PersonId]) -> None:
        if self._open:
            raise GroupDecisionAlreadyOpenException(f"{self._decision_id} is already open")
        if not voters:
            raise NoVotersGivenException(f"{self._decision_id} needs at least one voter")
        if not choices:
            raise NoChoicesGivenException(f"{self._decision_id} needs at least one choice")
        self._open = True
        self._voters = set(voters)
        self._choices = set(choices)
        self._ballots = {}
        self.add_event(
            GroupDecisionStartedEvent(
                **new_event_stamp(), decision_id=self._decision_id, voters=voters, choices=choices
            )
        )

    def cast(self, voter: PersonId, choice: VoteFor | Abstain) -> None:
        self._require_open()
        self._require_voter(voter)
        if voter in self._ballots:
            raise BallotAlreadyCastException(f"{voter} has already cast in {self._decision_id}")
        if isinstance(choice, Abstain) and not self._abstain_allowed:
            raise AbstainNotAllowedException(f"{self._decision_id} does not allow abstaining")
        if isinstance(choice, VoteFor):
            self._require_choice(choice.person)
        self._ballots[voter] = choice
        self.add_event(BallotCastEvent(**new_event_stamp(), decision_id=self._decision_id, voter=voter, choice=choice))
        self._tally_if_everyone_cast()

    def withdraw_voter(self, voter: PersonId) -> None:
        if not self._open or voter not in self._voters:
            return
        self._voters.remove(voter)
        self._ballots.pop(voter, None)
        self.add_event(VoterWithdrawnEvent(**new_event_stamp(), decision_id=self._decision_id, voter=voter))
        self._tally_if_everyone_cast()

    def withdraw_choice(self, choice: PersonId) -> None:
        if not self._open or choice not in self._choices:
            return
        self._choices.remove(choice)
        returned_to = frozenset(voter for voter, ballot in self._ballots.items() if ballot == VoteFor(choice))
        for voter in returned_to:
            del self._ballots[voter]
        self.add_event(
            ChoiceWithdrawnEvent(
                **new_event_stamp(), decision_id=self._decision_id, choice=choice, returned_to=returned_to
            )
        )

    def close(self) -> None:
        if not self._open:
            return
        self._tally()

    def is_open(self) -> bool:
        return self._open

    def _tally_if_everyone_cast(self) -> None:
        if self._voters <= self._ballots.keys():
            self._tally()

    def _tally(self) -> None:
        self._open = False
        ballots = frozenset(Ballot(voter, choice) for voter, choice in self._ballots.items())
        abstentions = sum(1 for choice in self._ballots.values() if isinstance(choice, Abstain))
        votes = Counter(choice.person for choice in self._ballots.values() if isinstance(choice, VoteFor))
        top = max(votes.values(), default=0)
        leaders = [person for person, count in votes.items() if count == top]
        if len(leaders) == 1 and top > abstentions:
            self.add_event(
                GroupDecisionReachedEvent(
                    **new_event_stamp(), decision_id=self._decision_id, chosen=leaders[0], ballots=ballots
                )
            )
            return
        self.add_event(
            GroupDecisionUnresolvedEvent(**new_event_stamp(), decision_id=self._decision_id, ballots=ballots)
        )

    def _require_open(self) -> None:
        if not self._open:
            raise GroupDecisionNotOpenException(f"{self._decision_id} is not open")

    def _require_voter(self, voter: PersonId) -> None:
        if voter not in self._voters:
            raise VoterNotInDecisionException(f"{voter} is not a voter in {self._decision_id}")

    def _require_choice(self, choice: PersonId) -> None:
        if choice not in self._choices:
            raise ChoiceNotInDecisionException(f"{choice} is not a choice in {self._decision_id}")
