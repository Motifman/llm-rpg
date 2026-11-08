from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson
from ai_rpg_world.game_world.domain.condition.aggregate_readings import GroupMembershipReading
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure, NoText
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.failure_texts import own_failure
from ai_rpg_world.game_world.domain.condition.leaf_condition import LeafCondition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Subject, SubjectKind
from ai_rpg_world.game_world.domain.declaration.character.group_declaration import (
    GroupDeclaration,
    MembershipVisibility,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class IsMemberCondition(LeafCondition):
    who: Subject
    group: GroupDeclaration
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.membership().is_member(self.who.person_in(trigger), self.group)

    def _requirements_besides_text(self) -> Requirements:
        return replace(self.who.requirements(), may_hide_membership=self._may_hide_from_actor())

    def _may_hide_from_actor(self) -> bool:
        visibility = self.group.grouping.visibility
        if visibility is MembershipVisibility.EVERYONE:
            return False
        return not (
            visibility is MembershipVisibility.SELF_ONLY
            and self.who.requirements().subjects == frozenset({SubjectKind.ACTOR})
        )

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        if self.holds(facts, trigger):
            return None
        acting_person = trigger.acting_person()
        if isinstance(acting_person, NoActingPerson):
            return own_failure(self.failure_text, trigger)
        if not self._is_known_to(acting_person, self.who.person_in(trigger), facts.membership()):
            return HiddenFailure(failed_part=ConditionPath.root())
        return own_failure(self.failure_text, trigger)

    def _is_known_to(self, acting_person: PersonId, person: PersonId, membership: GroupMembershipReading) -> bool:
        visibility = self.group.grouping.visibility
        return (
            visibility is MembershipVisibility.EVERYONE
            or (visibility is MembershipVisibility.SELF_ONLY and acting_person == person)
            or (self.group.members_know_each_other and membership.is_member(acting_person, self.group))
        )
