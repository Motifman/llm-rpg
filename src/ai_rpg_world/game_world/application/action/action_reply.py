from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import TextWithPeople
from ai_rpg_world.game_world.application.observation_exit import text_with_people
from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.people import TextAboutPeople
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class ActionDone:
    attempt: ActionAttempt
    done_text: TextAboutPeople
    summary: TextAboutPeople

    def was_waiting(self) -> bool:
        return self.attempt.is_waiting()

    def succeeded(self) -> bool:
        return True

    def actor(self) -> PersonId:
        return self.attempt.actor

    def result_for_actor(self, view: PeopleAsSeen) -> str | TextWithPeople:
        return text_with_people(self.done_text.seen_by(view))

    def summary_for_actor(self, design: WorldDesign, facts: WorldFacts, view: PeopleAsSeen) -> TextWithPeople:
        return text_with_people(self.summary.seen_by(view))


@final
@dataclass(frozen=True)
class ActionRefused:
    refusal: ActionRefusal

    def was_waiting(self) -> bool:
        return False

    def succeeded(self) -> bool:
        return False

    def actor(self) -> PersonId:
        return self.refusal.attempt.actor

    def result_for_actor(self, view: PeopleAsSeen) -> str | TextWithPeople:
        return text_with_people(self.refusal.text.seen_by(view))

    def summary_for_actor(self, design: WorldDesign, facts: WorldFacts, view: PeopleAsSeen) -> TextWithPeople | None:
        attempt = self.refusal.attempt
        situation = ActorSituation.of(attempt, facts)
        # 断られるあいだに品物を使い切られると、品物の名前を引けないので要約を出さない
        if not situation.knows_every_item_of(attempt):
            return None
        return text_with_people(attempt.summary_in(design, situation).seen_by(view))


ActionReply = ActionDone | ActionRefused
