from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.objects_and_items.where_item_was import CarriedBy, LyingAt, WhereItemWas
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
class ItemsRunningOut:
    def __init__(self, world: WorldAggregates) -> None:
        self._world = world

    def run_out_carried_by(self, person: PersonId, now: WorldTick) -> None:
        inventory = self._world.inventory(person)
        self._run_out_aged(now, CarriedBy(person), inventory.items(), inventory.give_up)

    def run_out_lying_at(self, spot: SpotId, now: WorldTick) -> None:
        ground = self._world.ground_items(spot)
        self._run_out_aged(now, LyingAt(spot), ground.items(), ground.take)

    def _run_out_aged(
        self,
        now: WorldTick,
        where: WhereItemWas,
        items: tuple[ItemInstanceId, ...],
        let_go: Callable[[ItemInstanceId], None],
    ) -> None:
        for item_id in items:
            item = self._world.item(item_id)
            if item.has_run_out(now):
                let_go(item_id)
                item.run_out(now, where)
                self._world.take_item_out_of_world(item_id)
