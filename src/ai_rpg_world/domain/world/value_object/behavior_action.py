from dataclasses import dataclass
from typing import Optional
from ai_rpg_world.domain.world.enum.world_enum import BehaviorActionType
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


@dataclass(frozen=True)
class BehaviorAction:
    """AIが決定した具体的なアクション"""
    action_type: BehaviorActionType
    coordinate: Optional[Coordinate] = None
    skill_slot_index: Optional[int] = None

    @classmethod
    def move(cls, coordinate: Coordinate) -> "BehaviorAction":
        return cls(action_type=BehaviorActionType.MOVE, coordinate=coordinate)

    @classmethod
    def use_skill(cls, slot_index: int) -> "BehaviorAction":
        return cls(action_type=BehaviorActionType.USE_SKILL, skill_slot_index=slot_index)

    @classmethod
    def wait(cls) -> "BehaviorAction":
        return cls(action_type=BehaviorActionType.WAIT)
