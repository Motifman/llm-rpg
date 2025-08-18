from typing import Dict, List, Optional
from dataclasses import dataclass
import random
from src.domain.battle.battle_enum import ParticipantType
from src.domain.battle.combat_entity import CombatEntity


@dataclass
class TurnEntry:
    entity_id: int
    participant_type: ParticipantType
    speed: int
    priority: int = 0


class TurnOrderService:
    """ターン順序計算のドメインサービス"""
    
    def calculate_initial_turn_order(self, participants: Dict[int, CombatEntity]) -> List[TurnEntry]:
        """初期ターン順序を計算"""
        entries = []
        
        for entity_id, entity in participants.items():
            participant_type = self._determine_participant_type(entity)
            entries.append(TurnEntry(
                entity_id=entity_id,
                participant_type=participant_type,
                speed=entity.speed,
                priority=self._calculate_priority(entity)
            ))
        
        # 速度 -> 優先度 -> ランダムの順でソート
        entries.sort(key=lambda x: (x.speed, x.priority, random.random()), reverse=True)
        return entries
    
    def recalculate_turn_order_for_next_round(self, current_participants: Dict[int, CombatEntity], 
                                            previous_order: List[TurnEntry]) -> List[TurnEntry]:
        """次ラウンドのターン順序を再計算"""
        # 生存者のみでフィルタリング
        alive_participants = {
            entity_id: entity for entity_id, entity in current_participants.items()
            if entity.is_alive()
        }
        
        return self.calculate_initial_turn_order(alive_participants)
    
    def get_next_actor(self, turn_order: List[TurnEntry], current_index: int) -> Optional[TurnEntry]:
        """次のアクターを取得"""
        if current_index + 1 < len(turn_order):
            return turn_order[current_index + 1]
        return None  # ラウンド終了
    
    def _determine_participant_type(self, entity: CombatEntity) -> ParticipantType:
        """エンティティタイプの判定"""
        from src.domain.player.player import Player
        from src.domain.monster.monster import Monster
        
        if isinstance(entity, Player):
            return ParticipantType.PLAYER
        elif isinstance(entity, Monster):
            return ParticipantType.MONSTER
        else:
            raise ValueError(f"Unknown entity type: {type(entity)}")
    
    def _calculate_priority(self, entity: CombatEntity) -> int:
        """同速度時の優先度計算"""
        # プレイヤーを優先、または特殊な優先度ルール
        from src.domain.player.player import Player
        return 1 if isinstance(entity, Player) else 0