from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import reduce
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.trigger import EachPersonOf
from ai_rpg_world.game_world.domain.condition.condition import (
    AwaitsArguments,
    Condition,
    FailureReason,
    HiddenFailure,
    NoText,
)
from ai_rpg_world.game_world.domain.condition.failure_texts import (
    explains,
    failure_of_all_children,
    failure_of_child,
    own_failure,
    placeholder_requirements,
)
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


def _combined(*parts: Requirements) -> Requirements:
    return reduce(Requirements.combined_with, parts, Requirements.nothing())


_Verdict = FailureReason | HiddenFailure | AwaitsArguments | None


def _every_holds_before_arguments(
    verdicts: Iterable[tuple[int, Trigger, _Verdict]], failure_text: TextWithUnassignedPeople | NoText
) -> _Verdict:
    awaits = False
    for position, child_trigger, verdict in verdicts:
        if isinstance(verdict, AwaitsArguments):
            awaits = True
        elif verdict is not None:
            return failure_of_child(verdict, position, failure_text, child_trigger)
    return AwaitsArguments() if awaits else None


def _some_holds_before_arguments(
    verdicts: Iterable[_Verdict], failure_text: TextWithUnassignedPeople | NoText, trigger: Trigger
) -> _Verdict:
    reasons: list[FailureReason | HiddenFailure] = []
    awaits = False
    for verdict in verdicts:
        if verdict is None:
            return None
        if isinstance(verdict, AwaitsArguments):
            awaits = True
        else:
            reasons.append(verdict)
    return AwaitsArguments() if awaits else failure_of_all_children(reasons, failure_text, trigger)


def _selected_in_world_order(people: PeopleSelection, facts: WorldFacts, trigger: Trigger) -> tuple[PersonId, ...]:
    # 偶然を引く順と、最初に偽になった人を毎回同じにするため、frozenset ではなく世界の並びでたどる。
    selected = people.select(facts, trigger)
    return tuple(person for person in facts.people() if person in selected)


@final
@dataclass(frozen=True)
class AllOfCondition:
    children: tuple[Condition, ...]
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return all(child.holds(facts, trigger) for child in self.children)

    def requirements(self) -> Requirements:
        return _combined(
            *(child.requirements() for child in self.children), placeholder_requirements(self.failure_text)
        )

    def explains_failure(self) -> bool:
        return explains(self.failure_text)

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        for position, child in enumerate(self.children):
            reason = child.failure_reason(facts, trigger)
            if reason is not None:
                return failure_of_child(reason, position, self.failure_text, trigger)
        return None

    def failure_reason_before_arguments(self, facts: WorldFacts, trigger: Trigger) -> _Verdict:
        return _every_holds_before_arguments(
            (
                (position, trigger, child.failure_reason_before_arguments(facts, trigger))
                for position, child in enumerate(self.children)
            ),
            self.failure_text,
        )


@final
@dataclass(frozen=True)
class AnyOfCondition:
    children: tuple[Condition, ...]
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return any(child.holds(facts, trigger) for child in self.children)

    def requirements(self) -> Requirements:
        return _combined(
            *(child.requirements() for child in self.children), placeholder_requirements(self.failure_text)
        )

    def explains_failure(self) -> bool:
        return explains(self.failure_text)

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        reasons: list[FailureReason | HiddenFailure] = []
        for child in self.children:
            reason = child.failure_reason(facts, trigger)
            if reason is None:
                return None
            reasons.append(reason)
        return failure_of_all_children(reasons, self.failure_text, trigger)

    def failure_reason_before_arguments(self, facts: WorldFacts, trigger: Trigger) -> _Verdict:
        return _some_holds_before_arguments(
            (child.failure_reason_before_arguments(facts, trigger) for child in self.children),
            self.failure_text,
            trigger,
        )


@final
@dataclass(frozen=True)
class NotCondition:
    child: Condition
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return not self.child.holds(facts, trigger)

    def requirements(self) -> Requirements:
        return self.child.requirements().combined_with(placeholder_requirements(self.failure_text))

    def explains_failure(self) -> bool:
        return explains(self.failure_text)

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        if self.holds(facts, trigger):
            return None
        return own_failure(self.failure_text, trigger)

    def failure_reason_before_arguments(self, facts: WorldFacts, trigger: Trigger) -> _Verdict:
        verdict = self.child.failure_reason_before_arguments(facts, trigger)
        if isinstance(verdict, AwaitsArguments):
            return verdict
        if verdict is None:
            return own_failure(self.failure_text, trigger)
        return None


@final
@dataclass(frozen=True)
class ForSomeoneCondition:
    people: PeopleSelection
    condition: Condition
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return any(
            self.condition.holds(facts, EachPersonOf(trigger, person))
            for person in _selected_in_world_order(self.people, facts, trigger)
        )

    def requirements(self) -> Requirements:
        return _combined(
            self.people.requirements(),
            self.condition.requirements().without_subject(SubjectKind.EACH_PERSON),
            placeholder_requirements(self.failure_text),
        )

    def explains_failure(self) -> bool:
        return explains(self.failure_text)

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        reasons: list[FailureReason | HiddenFailure] = []
        for person in _selected_in_world_order(self.people, facts, trigger):
            reason = self.condition.failure_reason(facts, EachPersonOf(trigger, person))
            if reason is None:
                return None
            reasons.append(reason)
        return failure_of_all_children(reasons, self.failure_text, trigger)

    def failure_reason_before_arguments(self, facts: WorldFacts, trigger: Trigger) -> _Verdict:
        return _some_holds_before_arguments(
            (
                self.condition.failure_reason_before_arguments(facts, EachPersonOf(trigger, person))
                for person in _selected_in_world_order(self.people, facts, trigger)
            ),
            self.failure_text,
            trigger,
        )


@final
@dataclass(frozen=True)
class ForEveryoneCondition:
    people: PeopleSelection
    condition: Condition
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return all(
            self.condition.holds(facts, EachPersonOf(trigger, person))
            for person in _selected_in_world_order(self.people, facts, trigger)
        )

    def requirements(self) -> Requirements:
        inside = self.condition.requirements().combined_with(placeholder_requirements(self.failure_text))
        return self.people.requirements().combined_with(inside.without_subject(SubjectKind.EACH_PERSON))

    def explains_failure(self) -> bool:
        return explains(self.failure_text)

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        for person in _selected_in_world_order(self.people, facts, trigger):
            each_person = EachPersonOf(trigger, person)
            reason = self.condition.failure_reason(facts, each_person)
            if reason is not None:
                return failure_of_child(reason, 0, self.failure_text, each_person)
        return None

    def failure_reason_before_arguments(self, facts: WorldFacts, trigger: Trigger) -> _Verdict:
        each_people = (
            EachPersonOf(trigger, person) for person in _selected_in_world_order(self.people, facts, trigger)
        )
        return _every_holds_before_arguments(
            (
                (0, each_person, self.condition.failure_reason_before_arguments(facts, each_person))
                for each_person in each_people
            ),
            self.failure_text,
        )
