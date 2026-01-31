from dataclasses import dataclass
from typing import List, Optional
from ai_rpg_world.domain.battle.battle_enum import ParticipantType, StatusEffectType
from ai_rpg_world.domain.battle.battle_action import ActionType
from datetime import datetime


@dataclass
class TurnRecord:
    """ターン記録"""
    turn_number: int
    actor_id: int
    actor_type: ParticipantType
    action_type: ActionType
    target_id: Optional[int]
    damage_dealt: int
    healing_done: int
    status_effects_applied: List[StatusEffectType]
    timestamp: datetime