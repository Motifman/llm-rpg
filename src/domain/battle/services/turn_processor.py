"""
ターン処理を担当するドメインサービス

責務:
- ターン開始処理の共通ロジック
- ターン終了処理の共通ロジック
- 戦闘終了条件チェック後の処理
"""
from typing import Optional, Protocol
from src.domain.battle.battle import Battle
from src.domain.battle.battle_enum import ParticipantType
from src.domain.battle.battle_result import TurnStartResult, TurnEndResult
from src.domain.battle.turn_order_service import TurnEntry
from src.domain.battle.combat_state import CombatState


class BattleLogicServiceProtocol(Protocol):
    """BattleLogicServiceのプロトコル（循環参照回避）"""
    
    def process_on_turn_start(self, actor_combat_state: CombatState) -> TurnStartResult:
        ...
    
    def process_on_turn_end(self, actor_combat_state: CombatState) -> TurnEndResult:
        ...


class TurnProcessor:
    """ターン処理ドメインサービス"""
    
    def __init__(self, battle_logic_service: BattleLogicServiceProtocol):
        self._battle_logic_service = battle_logic_service
    
    def process_turn_start(self, battle: Battle, actor: TurnEntry) -> TurnStartResult:
        """
        ターン開始処理
        
        Args:
            battle: 戦闘エンティティ
            actor: 現在のアクター
            
        Returns:
            TurnStartResult: ターン開始結果
            
        Raises:
            ValueError: アクターの戦闘状態が見つからない場合
        """
        participant_type, entity_id = actor.participant_key
        actor_combat_state = battle.get_combat_state(participant_type, entity_id)
        
        if not actor_combat_state:
            raise ValueError(f"Combat state not found for actor: {participant_type}, {entity_id}")
        
        # ターン開始時の状態異常・バフ処理
        turn_start_result = self._battle_logic_service.process_on_turn_start(actor_combat_state)
        battle.apply_turn_start_result(turn_start_result)
        
        return turn_start_result
    
    def process_turn_end(self, battle: Battle, actor: TurnEntry) -> TurnEndResult:
        """
        ターン終了処理
        
        Args:
            battle: 戦闘エンティティ
            actor: 現在のアクター
            
        Returns:
            TurnEndResult: ターン終了結果
            
        Raises:
            ValueError: アクターの戦闘状態が見つからない場合
        """
        participant_type, entity_id = actor.participant_key
        actor_combat_state = battle.get_combat_state(participant_type, entity_id)
        
        if not actor_combat_state:
            raise ValueError(f"Combat state not found for actor: {participant_type}, {entity_id}")
        
        # ターン終了時の状態異常・バフ処理
        turn_end_result = self._battle_logic_service.process_on_turn_end(actor_combat_state)
        battle.apply_turn_end_result(turn_end_result)
        
        return turn_end_result
    
    def check_and_handle_battle_end(self, battle: Battle) -> bool:
        """
        戦闘終了条件をチェックし、終了処理を実行
        
        Args:
            battle: 戦闘エンティティ
            
        Returns:
            bool: 戦闘が終了した場合True
        """
        battle_result = battle.check_battle_end_conditions()
        if battle_result:
            battle.end_battle(battle_result)
            return True
        return False
    
    def advance_turn(self, battle: Battle, turn_end_result: Optional[TurnEndResult] = None) -> None:
        """
        次のターンに進める
        
        Args:
            battle: 戦闘エンティティ
            turn_end_result: ターン終了結果（オプション）
        """
        battle.advance_to_next_turn(turn_end_result)
