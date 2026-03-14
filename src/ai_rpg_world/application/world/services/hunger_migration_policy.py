from dataclasses import dataclass
from typing import Iterable, Optional

from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@dataclass(frozen=True)
class HungerMigrationCandidate:
    monster_id: MonsterId
    world_object_id: WorldObjectId
    hunger: float
    forage_threshold: float
    has_preferred_feed: bool
    spot_has_feed: bool


class HungerMigrationPolicy:
    """候補 facts だけから移住対象を 1 体選ぶ pure policy。"""

    def select_migrant(
        self,
        candidates: Iterable[HungerMigrationCandidate],
    ) -> Optional[HungerMigrationCandidate]:
        eligible = [
            candidate
            for candidate in candidates
            if candidate.hunger >= candidate.forage_threshold
            and candidate.has_preferred_feed
            and not candidate.spot_has_feed
        ]
        if not eligible:
            return None
        return max(eligible, key=lambda candidate: candidate.hunger)
