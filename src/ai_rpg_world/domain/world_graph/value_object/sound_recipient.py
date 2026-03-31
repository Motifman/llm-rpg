from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.sound_clarity import SoundClarityEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


@dataclass(frozen=True)
class SoundRecipient:
    """音が届いたエンティティとその明瞭さ"""

    entity_id: EntityId
    spot_id: SpotId
    clarity: SoundClarityEnum
