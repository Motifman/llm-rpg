from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
from ai_rpg_world.game_world.domain.action.common_rule_refusal import CommonRuleRefusal
from ai_rpg_world.game_world.domain.action.refusal_code import RefusalCode
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception import Background, BodilyStimulus, Stimulus
from ai_rpg_world.game_world.domain.value_object import ItemSpecId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import NotAtSpot, Occupant

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class PreconditionRefusal:
    failure: FailureReason | HiddenFailure


@final
@dataclass(frozen=True)
class WorldStateRefusal:
    code: RefusalCode


@final
@dataclass(frozen=True)
class ActionRefusal:
    attempt: ActionAttempt
    reason: CommonRuleRefusal | PreconditionRefusal | WorldStateRefusal
    text: TextAboutPeople

    def stimuli_at(
        self,
        design: WorldDesign,
        item_specs: Mapping[ItemInstanceId, ItemSpecId],
        where: SpotId | NotAtSpot,
        actor: Occupant,
        at: WorldTick,
    ) -> tuple[Stimulus, ...]:
        # 共通の規則で断られたときは、周りから見て何も起きていない (use_cases.md)。
        if not isinstance(self.reason, (PreconditionRefusal, WorldStateRefusal)):
            return ()
        situation = ActorSituation(at_spot=where, actor_as=actor, item_specs=item_specs)
        return self.attempt.witnessed_in(design, situation).failure_stimuli_at(where, actor, at)
