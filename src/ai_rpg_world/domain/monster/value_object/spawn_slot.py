"""スポーンスロットの値オブジェクト。1スロット＝この座標にこのテンプレートを1体まで出す単位。"""

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.monster.value_object.spawn_condition import SpawnCondition
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterRespawnValidationException


@dataclass(frozen=True)
class SpawnSlot:
    """
    スポーンスロット。このスポットのこの座標に、このテンプレートのモンスターを
    1体まで出現させる単位。条件を満たしたときに spawn または respawn で埋める。
    """
    spot_id: SpotId
    coordinate: Coordinate
    template_id: MonsterTemplateId
    weight: int = 1
    condition: Optional[SpawnCondition] = None
    max_concurrent: int = 1

    def __post_init__(self):
        if self.weight < 0:
            raise MonsterRespawnValidationException(
                f"SpawnSlot weight cannot be negative: {self.weight}"
            )
        if self.max_concurrent < 1:
            raise MonsterRespawnValidationException(
                f"SpawnSlot max_concurrent must be positive: {self.max_concurrent}"
            )
