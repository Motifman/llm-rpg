from __future__ import annotations

from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import DisplayName, SpotId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
class NamesInWorld:
    def __init__(self, facts: WorldFacts) -> None:
        self._facts = facts

    def spot_name(self, spot: SpotId) -> DisplayName:
        return self._facts.nouns().spot_of(spot).name

    def item_name(self, item: ItemInstanceId) -> DisplayName:
        return self._facts.nouns().item_spec_of(self._facts.item(item).spec_id).name
