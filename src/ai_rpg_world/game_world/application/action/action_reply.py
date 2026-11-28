from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import TextWithPeople
from ai_rpg_world.game_world.application.observation_exit import action_summary_of, text_with_people
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_outcome_for_actor import ActionOutcomeForActor
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class ActionDone:
    attempt: ActionAttempt
    outcome: ActionOutcomeForActor

    def was_waiting(self) -> bool:
        return self.attempt.is_waiting()

    def succeeded(self) -> bool:
        return True

    def actor(self) -> PersonId:
        return self.attempt.actor

    def result_for_actor(self, view: PeopleAsSeen) -> str | TextWithPeople:
        return text_with_people(self.outcome.result.seen_by(view))

    def summary_for_actor(self, view: PeopleAsSeen) -> TextWithPeople | None:
        return action_summary_of(self.outcome.summary, view)


@final
@dataclass(frozen=True)
class ActionRefused:
    refusal: ActionRefusal
    outcome: ActionOutcomeForActor

    def was_waiting(self) -> bool:
        return False

    def succeeded(self) -> bool:
        return False

    def actor(self) -> PersonId:
        return self.refusal.attempt.actor

    def result_for_actor(self, view: PeopleAsSeen) -> str | TextWithPeople:
        return text_with_people(self.outcome.result.seen_by(view))

    def summary_for_actor(self, view: PeopleAsSeen) -> TextWithPeople | None:
        return action_summary_of(self.outcome.summary, view)


ActionReply = ActionDone | ActionRefused
