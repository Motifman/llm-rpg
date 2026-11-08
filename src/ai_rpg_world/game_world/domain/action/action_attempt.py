from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, final

from ai_rpg_world.game_world.domain.action.acting_person import NoActingPerson
from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NotTogether, OutOfReach
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.person import FallCause
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import ObjectId, PersonId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, Occupant, PersonBody

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.aggregate_readings import PersonVitalsReading
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueRule


@final
@dataclass(frozen=True)
class LivingOnly:
    def admits_departed(self) -> bool:
        return False


@final
@dataclass(frozen=True)
class LivingOrDeparted:
    def admits_departed(self) -> bool:
        return True


ActorRequirement = LivingOnly | LivingOrDeparted


@final
@dataclass(frozen=True)
class WithPerson:
    person: PersonId

    def refusal_for(self, actor: Occupant, facts: WorldFacts) -> NotTogether | None:
        if facts.whereabouts().are_together(actor, PersonBody(self.person)):
            return None
        return NotTogether()


@final
@dataclass(frozen=True)
class WithObject:
    obj: ObjectId

    def refusal_for(self, actor: Occupant, facts: WorldFacts) -> NotTogether | OutOfReach | None:
        nouns = facts.nouns()
        obj = nouns.object_of(self.obj)
        whereabouts = facts.whereabouts()
        # 区画を渡さなければ、can_reach は物と同じ場所にいるかだけを答える
        if not whereabouts.can_reach(actor, obj, ()):
            return NotTogether()
        if not whereabouts.can_reach(actor, obj, nouns.sections_at(obj.spot_id)):
            return OutOfReach()
        return None


@final
@dataclass(frozen=True)
class WithGroundItem:
    item: ItemInstanceId

    def refusal_for(self, actor: Occupant, facts: WorldFacts) -> NotTogether | None:
        location = facts.whereabouts().location_of(actor)
        if isinstance(location, AtSpot) and facts.ground_items(location.spot).contains(self.item):
            return None
        return NotTogether()


CopresenceRequirement = WithPerson | WithObject | WithGroundItem


@final
@dataclass(frozen=True)
class UsesBody:
    def is_too_tiring_for(self, vitals: PersonVitalsReading, rule: FatigueRule) -> bool:
        return vitals.fatigue_reached_limit(rule)


@final
@dataclass(frozen=True)
class DoesNotUseBody:
    def is_too_tiring_for(self, vitals: PersonVitalsReading, rule: FatigueRule) -> bool:
        return False


Exertion = UsesBody | DoesNotUseBody


class ActionAttempt(Protocol):
    @property
    def actor(self) -> PersonId: ...

    def kind(self) -> ActionKind: ...

    def actor_requirement(self) -> ActorRequirement: ...

    def copresence_requirements(self) -> tuple[CopresenceRequirement, ...]: ...

    def exertion(self) -> Exertion: ...

    def person_as(self, kind: SubjectKind) -> PersonId: ...

    def this_item(self) -> ItemInstanceId: ...

    def acting_person(self) -> PersonId | NoActingPerson: ...

    def argument(self, name: ArgumentName) -> TextArgumentValue | ItemInstanceId: ...

    def fall_cause_for(self, victim: PersonId) -> FallCause: ...

    def can_start_while_busy(self) -> bool: ...

    def is_allowed_in(self, stage: WorldStageDeclaration) -> bool: ...
