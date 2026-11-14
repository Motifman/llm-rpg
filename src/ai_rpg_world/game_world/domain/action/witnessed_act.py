from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.exception.perception_exception import PerceivedItemSpecNotGivenException
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import DisplayName, ItemSpecId, PersonId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import NotAtSpot, Occupant

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.manner import Manner
    from ai_rpg_world.game_world.domain.declaration.verb.perception_declaration import PerceptionDeclaration
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
    from ai_rpg_world.game_world.domain.people import NameInText
    from ai_rpg_world.game_world.domain.perception import NoTarget, SoundSource, Stimulus


@final
@dataclass(frozen=True)
class WitnessedAct:
    perception: PerceptionDeclaration
    names: Mapping[str, NameInText]
    target: PersonId | NoTarget
    manner: Manner
    source: SoundSource

    def stimuli_at(self, where: SpotId | NotAtSpot, actor: Occupant, at: WorldTick) -> tuple[Stimulus, ...]:
        if isinstance(where, NotAtSpot):
            return ()
        return self.perception.seen_at(
            where, actor, self.names, at, target=self.target, manner=self.manner, source=self.source
        )


def item_names(
    items: tuple[ItemInstanceId, ...], item_specs: Mapping[ItemInstanceId, ItemSpecId], design: WorldDesign
) -> DisplayName:
    missing = [item.value for item in items if item not in item_specs]
    if missing:
        raise PerceivedItemSpecNotGivenException(f"the kinds of {missing} were not read when the act was done")
    names = tuple(design.nouns.item_spec_of(item_specs[item]).name for item in items)
    return design.built_in_action_perceptions.item_joiner.join(names)
