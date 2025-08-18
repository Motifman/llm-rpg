from typing import Dict, List, Optional, Set, Tuple, Any
from src.domain.battle.events.battle_events import (
    BattleStartedEvent,
    PlayerJoinedBattleEvent,
    PlayerLeftBattleEvent,
    TurnStartedEvent,
    TurnExecutedEvent,
    TurnEndedEvent,
    RoundStartedEvent,
    RoundEndedEvent,
    BattleEndedEvent,
    MonsterDefeatedEvent,
    PlayerDefeatedEvent,
    StatusEffectAppliedEvent,
    StatusEffectExpiredEvent,
    BuffAppliedEvent,
    BuffExpiredEvent,
)
from src.domain.battle.battle_result import BattleActionResult
from src.domain.common.domain_event import DomainEvent
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.battle.battle_enum import BattleResultType, BattleState, ParticipantType, StatusEffectType, BuffType
from src.domain.battle.combat_entity import CombatEntity
from src.domain.battle.turn_record import TurnRecord
from src.domain.battle.turn_order_service import TurnOrderService
from src.domain.battle.turn_order_service import TurnEntry
from src.domain.battle.battle_result import TurnEndResult


class Battle(AggregateRoot):
    """戦闘の集約ルート"""
    
    def __init__(
        self,
        battle_id: int,
        spot_id: int,
        initiating_player_id: int,
        monster_ids: List[int],
        max_players: int = 4,
        max_turns: int = 30,
    ):
        super().__init__()
        self._battle_id = battle_id
        self._spot_id = spot_id
        self._participant_player_ids: List[int] = [initiating_player_id]
        self._monster_ids: List[int] = monster_ids
        self._max_players = max_players
        self._max_turns = max_turns
        self._state = BattleState.WAITING
        
        # ==== ターン管理 ====
        self._turn_order_service = TurnOrderService()
        self._turn_order: List[TurnEntry] = []
        self._turn_history: List[TurnRecord] = []
        self._current_turn = 0
        self._current_round = 0
        self._current_turn_index = 0
        
        # ==== 戦闘結果管理 ====
        self._total_damage_dealt: Dict[Tuple[ParticipantType, int], int] = {}  # (participant_type, entity_id) -> total_damage
        self._total_healing_done: Dict[Tuple[ParticipantType, int], int] = {}  # (participant_type, entity_id) -> total_healing
        self._contribution_scores: Dict[int, int] = {}  # player_id -> contribution
        self._battle_statistics: Dict[str, Any] = {
            "total_damage_dealt": 0,
            "total_healing_done": 0,
            "total_critical_hits": 0,
            "total_status_effects_applied": 0,
            "total_buffs_applied": 0,
        }
        
        # ==== 逃走管理 ====
        self._escaped_player_ids: Set[int] = set()
        self._escaped_monster_ids: Set[int] = set()
        
        # ==== イベント管理 ====
        self._events: List[DomainEvent] = []
        
    def get_current_actor(self) -> TurnEntry:
        """現在のターンのアクター取得"""
        if not self._turn_order:
            raise ValueError("Turn order not calculated")
        
        return self._turn_order[self._current_turn_index]
    
    def get_next_actor(self) -> Optional[TurnEntry]:
        """次のアクター取得"""
        return self._turn_order_service.get_next_actor(self._turn_order, self._current_turn_index)

    def start_battle(self, all_participants: Dict[int, CombatEntity]):
        """戦闘開始"""
        self._state = BattleState.IN_PROGRESS
        
        # ターン順序を計算
        self._turn_order = self._turn_order_service.calculate_initial_turn_order(all_participants)
        self._current_turn_index = 0
        self._current_round = 1
        
        # 戦闘開始イベント発行
        self.add_event(BattleStartedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            spot_id=self._spot_id,
            player_ids=self._participant_player_ids,
            monster_ids=self._monster_ids,
            max_players=self._max_players,
            max_turns=self._max_turns,
            battle_config={
                "max_players": self._max_players,
                "max_turns": self._max_turns,
                "initial_participants": len(all_participants),
            }
        ))
        
        # ラウンド開始イベント発行
        self._emit_round_started_event(all_participants)

    def _emit_round_started_event(self, all_participants: Dict[int, CombatEntity]):
        """ラウンド開始イベントを発行"""
        turn_order_data = [(entry.entity_id, entry.participant_type) for entry in self._turn_order]
        remaining_participants = {
            ParticipantType.PLAYER: [pid for pid in self._participant_player_ids if pid in all_participants],
            ParticipantType.MONSTER: [mid for mid in self._monster_ids if mid in all_participants],
        }
        
        round_stats = {
            "total_participants": len(self._turn_order),
            "player_count": len(remaining_participants[ParticipantType.PLAYER]),
            "monster_count": len(remaining_participants[ParticipantType.MONSTER]),
        }
        
        self.add_event(RoundStartedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            round_number=self._current_round,
            turn_order=turn_order_data,
            remaining_participants=remaining_participants,
            round_stats=round_stats,
        ))

    def start_turn(self, actor: CombatEntity, participant_type: ParticipantType) -> None:
        """ターン開始処理"""
        can_act = True
        status_effects = []
        active_buffs = []
        messages = []
        
        # アクターの統計情報を取得
        actor_stats = self._get_entity_stats(actor)
        
        # ターン開始イベントを発行
        self.add_event(TurnStartedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            turn_number=self._current_turn,
            round_number=self._current_round,
            actor_id=actor.entity_id,
            participant_type=participant_type,
            actor_stats=actor_stats,
            can_act=can_act,
            status_effects=status_effects,
            active_buffs=active_buffs,
            messages=messages,
        ))

    def _get_entity_stats(self, entity: CombatEntity) -> Dict[str, Any]:
        """エンティティの統計情報を取得"""
        return {
            "entity_id": entity.entity_id,
            "name": entity.name,
            "hp": entity.hp,
            "max_hp": entity.max_hp,
            "mp": entity.mp,
            "max_mp": entity.max_mp,
            "attack": entity.attack,
            "defense": entity.defense,
            "speed": entity.speed,
            "level": getattr(entity, 'level', 1),
        }

    def advance_to_next_turn(self, all_participants: Dict[int, CombatEntity], turn_end_result: Optional[TurnEndResult] = None) -> bool:
        """次のターンに進む"""
        # 現在のターン終了イベントを発行
        current_actor = self.get_current_actor()
        if current_actor:
            self._emit_turn_ended_event(current_actor, all_participants, turn_end_result)
        
        self._current_turn_index += 1
        
        # ラウンド終了チェック
        if self._current_turn_index >= len(self._turn_order):
            return self._advance_to_next_round(all_participants)
        
        return True
    
    def _emit_turn_ended_event(self, actor_entry: TurnEntry, all_participants: Dict[int, CombatEntity], turn_end_result: Optional[TurnEndResult] = None):
        """ターン終了イベントを発行"""
        actor = all_participants.get(actor_entry.entity_id)
        if not actor:
            return
            
        actor_stats = self._get_entity_stats(actor)
        
        # TurnEndResultから情報を取得（ない場合はデフォルト値）
        if turn_end_result:
            damage_from_status_effects = turn_end_result.damage_from_status_effects
            healing_from_status_effects = turn_end_result.healing_from_status_effects
            expired_status_effects = turn_end_result.expired_status_effects
            expired_buffs = turn_end_result.expired_buffs
            messages = turn_end_result.messages
        else:
            damage_from_status_effects = 0
            healing_from_status_effects = 0
            expired_status_effects = []
            expired_buffs = []
            messages = []
        
        self.add_event(TurnEndedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            turn_number=self._current_turn,
            round_number=self._current_round,
            actor_id=actor_entry.entity_id,
            participant_type=actor_entry.participant_type,
            is_actor_defeated=not actor.is_alive(),
            damage_from_status_effects=damage_from_status_effects,
            healing_from_status_effects=healing_from_status_effects,
            expired_status_effects=expired_status_effects,
            expired_buffs=expired_buffs,
            final_actor_stats=actor_stats,
            messages=messages,
        ))
    
    def _advance_to_next_round(self, all_participants: Dict[int, CombatEntity]) -> bool:
        """次のラウンドに進む"""
        # ラウンド終了イベントを発行
        self._emit_round_ended_event(all_participants)
        
        self._current_round += 1
        self._current_turn_index = 0
        
        # ターン順序を再計算
        self._turn_order = self._turn_order_service.recalculate_turn_order_for_next_round(
            all_participants, self._turn_order
        )
        
        # 新しいラウンド開始イベントを発行
        if self._current_round <= self._max_turns and len(self._turn_order) > 0:
            self._emit_round_started_event(all_participants)
        
        return self._current_round <= self._max_turns and len(self._turn_order) > 0
    
    def _emit_round_ended_event(self, all_participants: Dict[int, CombatEntity]):
        """ラウンド終了イベントを発行"""
        round_summary = {
            "round_number": self._current_round,
            "total_turns_in_round": len(self._turn_order),
            "remaining_participants": len(self._turn_order),
        }
        
        next_round_turn_order = [(entry.entity_id, entry.participant_type) for entry in self._turn_order]
        
        self.add_event(RoundEndedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            round_number=self._current_round,
            round_summary=round_summary,
            next_round_turn_order=next_round_turn_order,
        ))
    
    def join_player(self, player_id: int, player_stats: Dict[str, Any]) -> bool:
        """プレイヤーが戦闘に参加"""
        if len(self._participant_player_ids) >= self._max_players:
            return False

        if player_id in self._participant_player_ids:
            return False
        
        self._participant_player_ids.append(player_id)
        self.add_event(PlayerJoinedBattleEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            player_id=player_id,
            join_turn=self._current_turn,
            player_stats=player_stats,
        ))
        return True
    
    def player_escape(self, player_id: int, final_stats: Dict[str, Any]) -> bool:
        """プレイヤーが戦闘から離脱"""
        if player_id not in self._participant_player_ids:
            return False
        
        self._participant_player_ids.remove(player_id)
        self._escaped_player_ids.add(player_id)
        
        contribution_score = self._contribution_scores.get(player_id, 0)

        self.add_event(PlayerLeftBattleEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            player_id=player_id,
            reason="escape",
            final_stats=final_stats,
            contribution_score=contribution_score,
        ))
        return True

    def execute_turn(
        self,
        actor_id: int,
        participant_type: ParticipantType,
        action_type: str,
        action_name: str,
        target_ids: List[int],
        target_participant_types: List[ParticipantType],
        battle_action_result: BattleActionResult
    ) -> None:
        """ターンを実行"""
        actor = self.get_current_actor()
        if actor.entity_id != actor_id or actor.participant_type != participant_type:
            raise ValueError(f"Invalid actor: {actor_id}, {participant_type}, {actor.entity_id}, {actor.participant_type}")
        
        # 統計情報を更新
        key = (participant_type, actor_id)
        self._total_damage_dealt[key] = self._total_damage_dealt.get(key, 0) + battle_action_result.total_damage
        self._total_healing_done[key] = self._total_healing_done.get(key, 0) + battle_action_result.total_healing
        
        # 戦闘統計を更新
        self._battle_statistics["total_damage_dealt"] += battle_action_result.total_damage
        self._battle_statistics["total_healing_done"] += battle_action_result.total_healing
        self._battle_statistics["total_critical_hits"] += sum(battle_action_result.critical_hits)
        self._battle_statistics["total_status_effects_applied"] += len(battle_action_result.applied_status_effects)
        self._battle_statistics["total_buffs_applied"] += len(battle_action_result.applied_buffs)
        
        # ターン実行イベントを発行
        self.add_event(TurnExecutedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            turn_number=self._current_turn,
            round_number=self._current_round,
            actor_id=actor_id,
            participant_type=participant_type,
            action_type=action_type,
            action_name=action_name,
            target_ids=target_ids,
            target_participant_types=target_participant_types,
            damage_dealt=battle_action_result.total_damage,
            healing_done=battle_action_result.total_healing,
            hp_consumed=battle_action_result.hp_consumed,
            mp_consumed=battle_action_result.mp_consumed,
            critical_hits=battle_action_result.critical_hits,
            compatibility_multipliers=battle_action_result.compatibility_multipliers,
            applied_status_effects=battle_action_result.applied_status_effects,
            applied_buffs=battle_action_result.applied_buffs,
            messages=battle_action_result.messages,
            success=battle_action_result.success,
            failure_reason=battle_action_result.failure_reason,
        ))
        
        # 状態異常・バフ適用イベントを発行
        self._emit_status_effect_events(battle_action_result, actor_id, participant_type)
        self._emit_buff_events(battle_action_result, actor_id, participant_type)
    
    def _emit_status_effect_events(self, battle_action_result: BattleActionResult, actor_id: int, actor_type: ParticipantType):
        """状態異常関連イベントを発行"""
        for target_id, status_effect_type, duration in battle_action_result.applied_status_effects:
            self.add_event(StatusEffectAppliedEvent.create(
                aggregate_id=self._battle_id,
                aggregate_type="battle",
                battle_id=self._battle_id,
                target_id=target_id,
                participant_type=ParticipantType.PLAYER if target_id in self._participant_player_ids else ParticipantType.MONSTER,
                status_effect_type=status_effect_type,
                duration=duration,
                applied_turn=self._current_turn,
                applied_round=self._current_round,
                applied_by_id=actor_id,
                applied_by_type=actor_type,
            ))
    
    def _emit_buff_events(self, battle_action_result: BattleActionResult, actor_id: int, actor_type: ParticipantType):
        """バフ関連イベントを発行"""
        for target_id, buff_type, multiplier, duration in battle_action_result.applied_buffs:
            self.add_event(BuffAppliedEvent.create(
                aggregate_id=self._battle_id,
                aggregate_type="battle",
                battle_id=self._battle_id,
                target_id=target_id,
                participant_type=ParticipantType.PLAYER if target_id in self._participant_player_ids else ParticipantType.MONSTER,
                buff_type=buff_type,
                multiplier=multiplier,
                duration=duration,
                applied_turn=self._current_turn,
                applied_round=self._current_round,
                applied_by_id=actor_id,
                applied_by_type=actor_type,
            ))
    
    def check_battle_end_conditions(self) -> Optional[BattleResultType]:
        """戦闘終了条件をチェック（IDベース）"""
        # プレイヤー全滅チェック
        if len(self._participant_player_ids) == 0:
            return BattleResultType.DEFEAT
        
        # モンスター全滅チェック
        if len(self._monster_ids) == 0:
            return BattleResultType.VICTORY
        
        # 最大ターン数チェック
        if self._current_round >= self._max_turns:
            return BattleResultType.DRAW
        
        return None
    
    def remove_defeated_participant(self, entity_id: int, entity_type: ParticipantType, final_stats: Dict[str, Any], defeated_by_id: int, defeated_by_type: ParticipantType):
        """撃破された参加者を削除"""
        if entity_type == ParticipantType.PLAYER:
            if entity_id in self._participant_player_ids:
                self._participant_player_ids.remove(entity_id)
                self.add_event(PlayerDefeatedEvent.create(
                    aggregate_id=self._battle_id,
                    aggregate_type="battle",
                    battle_id=self._battle_id,
                    player_id=entity_id,
                    defeated_by_monster_id=defeated_by_id,
                    defeat_turn=self._current_turn,
                    defeat_round=self._current_round,
                    final_player_stats=final_stats,
                    damage_dealt_by_defeater=0,  # BattleServiceから取得する必要がある
                ))
        elif entity_type == ParticipantType.MONSTER:
            if entity_id in self._monster_ids:
                self._monster_ids.remove(entity_id)
                self.add_event(MonsterDefeatedEvent.create(
                    aggregate_id=self._battle_id,
                    aggregate_type="battle",
                    battle_id=self._battle_id,
                    monster_id=entity_id,
                    monster_type_id=0,  # モンスタータイプIDは別途取得する必要がある
                    defeated_by_player_id=defeated_by_id,
                    defeat_turn=self._current_turn,
                    defeat_round=self._current_round,
                    drop_reward={},  # ドロップ報酬は別途計算する必要がある
                    final_monster_stats=final_stats,
                    damage_dealt_by_defeater=0,  # BattleServiceから取得する必要がある
                ))

    def end_battle(self, result_type: BattleResultType, winner_ids: List[int]) -> None:
        """戦闘を終了"""
        self._state = BattleState.COMPLETED
        
        # 戦闘終了イベントを発行
        self.add_event(BattleEndedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            spot_id=self._spot_id,
            result_type=result_type,
            winner_ids=winner_ids,
            participant_ids=self._participant_player_ids,
            total_turns=self._current_turn,
            total_rounds=self._current_round,
            total_rewards={"gold": 1000, "exp": 500},  # 計算ロジックは別途実装
            battle_statistics=self._battle_statistics,
            contribution_scores=self._contribution_scores,
        ))
    
    def update_contribution_score(self, player_id: int, score: int):
        """プレイヤーの貢献度スコアを更新"""
        self._contribution_scores[player_id] = self._contribution_scores.get(player_id, 0) + score