from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.exception.world_contents_exception import AggregateNotInWorldException
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import ItemSpecId, SpotId
from ai_rpg_world.game_world.domain.whereabouts import NotAtSpot, Occupant

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class ActorSituation:
    at_spot: SpotId | NotAtSpot
    actor_as: Occupant
    item_specs: Mapping[ItemInstanceId, ItemSpecId]

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_specs", MappingProxyType(dict(self.item_specs)))

    @classmethod
    def of(cls, attempt: ActionAttempt, facts: WorldFacts) -> ActorSituation:
        actor_as = facts.vitals(attempt.actor).occupant_in_world(facts.rules().departed_persons_act)
        return cls(
            at_spot=facts.whereabouts().spot_of(actor_as),
            actor_as=actor_as,
            item_specs=dict(_spec_of(item, facts) for item in attempt.items_handled() if _is_in_world(item, facts)),
        )


def _spec_of(item: ItemInstanceId, facts: WorldFacts) -> tuple[ItemInstanceId, ItemSpecId]:
    return item, facts.item(item).spec_id


def _is_in_world(item: ItemInstanceId, facts: WorldFacts) -> bool:
    # 断られた試みは、もう世界に無い品物 (拾われた、使い切った) を指していることがある
    try:
        facts.item(item)
    except AggregateNotInWorldException:
        return False
    return True
