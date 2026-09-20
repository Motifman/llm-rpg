from dataclasses import dataclass

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import PassageConditionTypeEnum


@dataclass(frozen=True)
class PassageCondition:
    """スポット間の通行条件"""

    condition_type: PassageConditionTypeEnum
    item_spec_id: ItemSpecId | None = None
    flag_name: str | None = None
    consume_item: bool = False
    failure_message: str = ""
