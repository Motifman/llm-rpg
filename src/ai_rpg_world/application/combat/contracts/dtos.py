from dataclasses import dataclass
from typing import List, Optional
from ai_rpg_world.domain.battle.battle_enum import StatusEffectType, ParticipantType


@dataclass
class StatusEffectDto:
    status_effect_type: StatusEffectType
    message: str


@dataclass
class PlayerActionDto:
    """プレイヤー行動データ"""
    battle_id: int
    player_id: int
    action_id: int
    target_ids: Optional[List[int]] = None
    target_participant_types: Optional[List[ParticipantType]] = None


@dataclass
class BattleStatusDto:
    """戦闘状態データ"""
    battle_id: int
    is_active: bool
    current_turn: int
    current_round: int
    player_count: int
    monster_count: int
    can_player_join: bool