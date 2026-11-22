from __future__ import annotations

from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.exception.person_exception import PersonNotAliveException
from ai_rpg_world.game_world.domain.objects_and_items.ground_items import GroundItems
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts.occupant import PersonBody

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
class ItemsChangingPlace:
    def __init__(self, world: WorldAggregates) -> None:
        self._world = world

    def pick_up(self, person: PersonId, item: ItemInstanceId, at: WorldTick) -> None:
        self._ground_under(person).take(item)
        self._world.inventory(person).receive(item, self._world.item(item).spec_id, at)

    def drop(self, person: PersonId, item: ItemInstanceId, at: WorldTick) -> None:
        self._world.inventory(person).give_up(item, at)
        self._ground_under(person).place(item)

    def hold(self, person: PersonId, item: ItemInstanceId) -> None:
        self._world.inventory(person).hold(item, self._world.item(item).hands_needed())

    def hand_over(self, giver: PersonId, receiver: PersonId, items: tuple[ItemInstanceId, ...], at: WorldTick) -> None:
        if not self._world.vitals(receiver).can_act():
            raise PersonNotAliveException(f"{receiver.value} cannot receive items while not alive")
        for item in items:
            self._world.inventory(giver).give_up(item, at)
            self._world.inventory(receiver).receive(item, self._world.item(item).spec_id, at)

    def _ground_under(self, person: PersonId) -> GroundItems:
        return self._world.ground_items(self._world.whereabouts().spot_standing_on(PersonBody(person)))
