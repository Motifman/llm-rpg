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
            item_specs={
                item: spec for item in attempt.items_handled() if (spec := _spec_in_world(item, facts)) is not None
            },
        )

    def knows_every_item_of(self, attempt: ActionAttempt) -> bool:
        return all(item in self.item_specs for item in attempt.items_handled())


def _spec_in_world(item: ItemInstanceId, facts: WorldFacts) -> ItemSpecId | None:
    # 断られた試みは、使い切って世界から出た品物を指していることがある
    try:
        return facts.item(item).spec_id
    except AggregateNotInWorldException:
        return None
