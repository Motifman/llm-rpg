from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import random
from ai_rpg_world.domain.battle.battle_enum import ParticipantType
from ai_rpg_world.domain.battle.combat_state import CombatState


@dataclass
class TurnEntry:
    participant_key: Tuple[ParticipantType, int]
    speed: int
    priority: int = 0


class TurnOrderService:
    """ターン順序計算のドメインサービス"""
    
    def calculate_initial_turn_order(self, combat_states: Dict[Tuple[ParticipantType, int], CombatState]) -> List[TurnEntry]:
        """初期ターン順序を計算"""
        entries = []
        
        for participant_key, combat_state in combat_states.items():
            entries.append(TurnEntry(
                participant_key=participant_key,
                speed=combat_state.calculate_current_speed(),
                priority=self._calculate_priority(combat_state)
            ))
        
        # 速度 -> 優先度 -> ランダムの順でソート
        entries.sort(key=lambda x: (x.speed, x.priority, random.random()), reverse=True)
        return entries
    
    def recalculate_turn_order_for_next_round(self, current_combat_states: Dict[Tuple[ParticipantType, int], CombatState], 
                                            previous_order: List[TurnEntry]) -> List[TurnEntry]:
        """次ラウンドのターン順序を再計算"""
        # 生存者のみでフィルタリング
        alive_participants = {
            participant_type: combat_state for participant_type, combat_state in current_combat_states.items()
            if combat_state.is_alive()
        }
        
        return self.calculate_initial_turn_order(alive_participants)
    
    def get_next_actor(self, turn_order: List[TurnEntry], current_index: int) -> Optional[TurnEntry]:
        """次のアクターを取得"""
        if current_index + 1 < len(turn_order):
            return turn_order[current_index + 1]
        return None  # ラウンド終了
    
    def _calculate_priority(self, combat_state: CombatState) -> int:
        """同速度時の優先度計算"""
        # プレイヤーを優先、または特殊な優先度ルール
        return 1 if combat_state.participant_type == ParticipantType.PLAYER else 0