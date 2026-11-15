from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar, final

from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates

_T = TypeVar("_T", covariant=True)
_R = TypeVar("_R")


class ByWhereItemWas(Protocol[_T]):
    def when_carried(self, person: PersonId) -> _T: ...

    def when_lying(self, spot: SpotId) -> _T: ...


@final
@dataclass(frozen=True)
class CarriedBy:
    person: PersonId

    def read(self, cases: ByWhereItemWas[_R]) -> _R:
        return cases.when_carried(self.person)

    def run_out_aged_items(self, world: WorldAggregates, now: WorldTick) -> None:
        inventory = world.inventory(self.person)
        _run_out_aged_items(world, now, self, inventory.items(), inventory.give_up)


@final
@dataclass(frozen=True)
class LyingAt:
    spot: SpotId

    def read(self, cases: ByWhereItemWas[_R]) -> _R:
        return cases.when_lying(self.spot)

    def run_out_aged_items(self, world: WorldAggregates, now: WorldTick) -> None:
        ground = world.ground_items(self.spot)
        _run_out_aged_items(world, now, self, ground.items(), ground.take)


WhereItemWas = CarriedBy | LyingAt


def _run_out_aged_items(
    world: WorldAggregates,
    now: WorldTick,
    where: WhereItemWas,
    items: tuple[ItemInstanceId, ...],
    let_go: Callable[[ItemInstanceId], None],
) -> None:
    for item_id in items:
        item = world.item(item_id)
        if item.has_run_out(now):
            let_go(item_id)
            item.run_out(now, where)
            world.take_item_out_of_world(item_id)
