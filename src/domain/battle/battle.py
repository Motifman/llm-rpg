from typing import Dict, List, Optional, Set, Tuple, Any
from src.domain.battle.events.battle_events import (
    BattleStartedEvent,
    PlayerJoinedBattleEvent,
    MonsterJoinedBattleEvent,
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
from src.domain.battle.battle_result import BattleActionResult, TurnStartResult, TurnEndResult
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.battle.battle_enum import BattleResultType, BattleState, ParticipantType
from src.domain.battle.combat_state import CombatState
from src.domain.battle.turn_record import TurnRecord
from src.domain.battle.turn_order_service import TurnOrderService
from src.domain.battle.turn_order_service import TurnEntry
from src.domain.player.player import Player
from src.domain.monster.monster import Monster
from src.domain.monster.drop_reward import EMPTY_REWARD
from src.domain.battle.battle_exception import BattleNotStartedException, BattleFullException, PlayerAlreadyInBattleException


# TODO: 最低限の要素のみを一旦実装しなおす
# TODO: イベント機能は一旦削除して、ドメインロジックのみを実装する
class Battle(AggregateRoot):
    """戦闘の集約ルート"""
    
    def __init__(
        self,
        battle_id: int,
        spot_id: int,
        players: List[Player],
        monsters: List[Monster],
        max_players: int = 4,
        max_monsters: int = 4,
        max_rounds: int = 10,
    ):
        super().__init__()
        if max_players < 1:
            raise ValueError("max_players must be greater than 0")
        if max_monsters < 1:
            raise ValueError("max_monsters must be greater than 0")
        if max_rounds < 1:
            raise ValueError("max_rounds must be greater than 0")
        
        self._battle_id = battle_id
        self._spot_id = spot_id
        self._max_players = max_players
        self._max_monsters = max_monsters
        self._max_rounds = max_rounds
        self._combat_states: Dict[Tuple[ParticipantType, int], CombatState] = {}
        self._player_ids: Set[int] = set()
        self._monster_ids: Set[int] = set()
        self._monster_type_ids: Set[int] = set()
        self._monster_count_for_identification = 0  # 同一モンスターを識別するためのカウンター

        # 貢献度スコア管理
        self._contribution_scores: Dict[int, int] = {}

        # 逃走管理
        self._escaped_player_ids: Set[int] = set()

        for player in players:
            self._add_player(player)
        
        for monster in monsters:
            self._add_monster(monster)
        self._state = BattleState.WAITING
        
        self._turn_order_service = TurnOrderService()
        self._turn_order: List[TurnEntry] = []
        self._turn_history: List[TurnRecord] = []
        self._current_turn = 0
        self._current_round = 0
        self._current_turn_index = 0
        
        # ターンロック機能（非同期戦闘ループ制御用）
        self._turn_locked = False
        self._waiting_for_player_action = False
    
    @property
    def battle_id(self) -> int:
        return self._battle_id
    
    @property
    def spot_id(self) -> int:
        return self._spot_id
    
    def is_in_progress(self) -> bool:
        """戦闘が進行中かどうかを判定"""
        return self._state == BattleState.IN_PROGRESS
    
    def is_turn_locked(self) -> bool:
        """ターンがロックされているかどうか"""
        return self._turn_locked
    
    def is_waiting_for_player_action(self) -> bool:
        """プレイヤー行動待機中かどうか"""
        return self._waiting_for_player_action
    
    def lock_turn_for_player_action(self, player_id: int) -> None:
        """プレイヤー行動のためにターンをロック"""
        current_actor = self.get_current_actor()
        participant_type, entity_id = current_actor.participant_key
        
        if participant_type != ParticipantType.PLAYER or entity_id != player_id:
            raise ValueError(f"Cannot lock turn for player {player_id}, current actor is {participant_type}:{entity_id}")
        
        self._turn_locked = True
        self._waiting_for_player_action = True
    
    def unlock_turn_after_player_action(self, player_id: int) -> None:
        """プレイヤー行動完了後にターンをアンロック"""
        if not self._waiting_for_player_action:
            raise ValueError("Not waiting for player action")
        
        current_actor = self.get_current_actor()
        participant_type, entity_id = current_actor.participant_key
        
        if participant_type != ParticipantType.PLAYER or entity_id != player_id:
            raise ValueError(f"Cannot unlock turn for player {player_id}, current actor is {participant_type}:{entity_id}")
        
        self._turn_locked = False
        self._waiting_for_player_action = False
    
    def can_advance_turn(self) -> bool:
        """ターンを進めることができるかどうか"""
        return not self._turn_locked
    
    def _add_monster(self, monster: Monster):
        if len(self._monster_ids) >= self._max_monsters:
            raise BattleFullException("Too many monsters")
        self._monster_count_for_identification += 1
        self._combat_states[(ParticipantType.MONSTER, self._monster_count_for_identification)] = CombatState.from_monster(monster, self._monster_count_for_identification)
        self._monster_ids.add(self._monster_count_for_identification)
        self._monster_type_ids.add(monster.monster_type_id)
    
    def _add_player(self, player: Player):
        if len(self._player_ids) >= self._max_players:
            raise BattleFullException("Too many players")
        if player.player_id in self._player_ids:
            raise PlayerAlreadyInBattleException("Player already in battle")
        self._combat_states[(ParticipantType.PLAYER, player.player_id)] = CombatState.from_player(player, player.player_id)
        self._player_ids.add(player.player_id)
        self._contribution_scores[player.player_id] = 0
    
    def get_combat_state(self, participant_type: ParticipantType, entity_id: int) -> Optional[CombatState]:
        """戦闘状態を取得"""
        return self._combat_states.get((participant_type, entity_id))
    
    def get_combat_states(self) -> Dict[Tuple[ParticipantType, int], CombatState]:
        """戦闘状態を取得"""
        return self._combat_states
    
    def get_player_ids(self) -> List[int]:
        """プレイヤーのIDを取得"""
        return [player_id for player_id in self._player_ids]
    
    def get_monster_type_ids(self) -> List[int]:
        """モンスターの種類のIDを取得"""
        return [monster_type_id for monster_type_id in self._monster_type_ids]
    
    def get_current_actor(self) -> TurnEntry:
        """現在のターンのアクター取得"""
        if not self._turn_order:
            raise ValueError("Turn order not calculated")
        
        return self._turn_order[self._current_turn_index]
        
    def start_battle(self):
        if self._state != BattleState.WAITING:
            raise BattleNotStartedException()

        self._state = BattleState.IN_PROGRESS

        # ターン順序を計算
        self._turn_order = self._turn_order_service.calculate_initial_turn_order(self._combat_states)
        self._current_turn_index = 0
        self._current_round = 1

        # 戦闘開始イベント発行
        self._emit_battle_started_event()

        # ラウンド開始イベント発行
        self._emit_round_started_event()

    def _emit_battle_started_event(self):
        """戦闘開始イベントを発行"""
        self.add_event(BattleStartedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            spot_id=self._spot_id,
            player_ids=list(self._player_ids),
            monster_ids=list(self._monster_ids),
            max_players=self._max_players,
            max_turns=self._max_rounds,
            battle_config={
                "max_players": self._max_players,
                "max_rounds": self._max_rounds,
                "initial_players": len(self._player_ids),
                "initial_monsters": len(self._monster_ids),
            }
        ))

    def _emit_round_started_event(self):
        """ラウンド開始イベントを発行"""
        turn_order_data = [(entry.participant_key[0], entry.participant_key[1]) for entry in self._turn_order]
        remaining_participants = {
            ParticipantType.PLAYER: [entity_id for participant_type, entity_id in self._combat_states.keys()
                                   if participant_type == ParticipantType.PLAYER and
                                   self._combat_states[(participant_type, entity_id)].is_alive()],
            ParticipantType.MONSTER: [entity_id for participant_type, entity_id in self._combat_states.keys()
                                    if participant_type == ParticipantType.MONSTER and
                                    self._combat_states[(participant_type, entity_id)].is_alive()],
        }

        round_stats = {
            "total_participants": len(self._turn_order),
            "player_count": len(remaining_participants[ParticipantType.PLAYER]),
            "monster_count": len(remaining_participants[ParticipantType.MONSTER]),
            "round_number": self._current_round,
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

    def start_turn(self) -> None:
        """ターン開始処理"""
        # ターン数を更新
        self._current_turn += 1

        # 自分が防御状態であれば解除する
        current_actor = self.get_current_actor()
        if current_actor:
            participant_type, entity_id = current_actor.participant_key
            combat_state = self._combat_states.get((participant_type, entity_id))
            if combat_state and combat_state.is_defending:
                combat_state = combat_state.without_defend()
                self._combat_states[(participant_type, entity_id)] = combat_state

        # ターン開始イベント発行
        self._emit_turn_started_event(current_actor)

    def _emit_turn_started_event(self, current_actor: TurnEntry):
        """ターン開始イベントを発行"""
        if not current_actor:
            return

        participant_type, entity_id = current_actor.participant_key
        combat_state = self._combat_states.get((participant_type, entity_id))
        if not combat_state:
            return

        # アクターの統計情報を取得
        actor_stats = {
            "entity_id": combat_state.entity_id,
            "name": combat_state.name,
            "hp": combat_state.current_hp.value,
            "max_hp": combat_state.current_hp.max_hp,
            "mp": combat_state.current_mp.value,
            "max_mp": combat_state.current_mp.max_mp,
            "attack": combat_state.attack,
            "defense": combat_state.defense,
            "speed": combat_state.speed,
            "level": 1,  # TODO: レベル情報を追加する必要がある場合
        }

        # 状態異常とバフの情報を取得
        status_effects = list(combat_state.status_effects.keys())
        active_buffs = list(combat_state.buffs.keys())

        self.add_event(TurnStartedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            turn_number=self._current_turn,
            round_number=self._current_round,
            actor_id=entity_id,
            participant_type=participant_type,
            actor_stats=actor_stats,
            can_act=combat_state.can_act,
            status_effects=status_effects,
            active_buffs=active_buffs,
            messages=[],
        ))

    def advance_to_next_turn(self, turn_end_result: Optional[TurnEndResult] = None) -> bool:
        """次のターンに進む"""
        # 現在のターン終了イベントを発行
        current_actor = self.get_current_actor()
        if current_actor:
            self._emit_turn_ended_event(current_actor, turn_end_result)
        
        self._current_turn_index += 1
        
        # ラウンド終了チェック
        if self._current_turn_index >= len(self._turn_order):
            return self._advance_to_next_round()
        
        return True
    
    def _emit_turn_ended_event(self, actor_entry: TurnEntry, turn_end_result: Optional[TurnEndResult] = None):
        """ターン終了イベントを発行"""
        participant_type, entity_id = actor_entry.participant_key
        combat_state = self._combat_states.get((participant_type, entity_id))
        if not combat_state:
            return

        # 最終アクター統計を取得
        final_actor_stats = {
            "entity_id": combat_state.entity_id,
            "name": combat_state.name,
            "hp": combat_state.current_hp.value,
            "max_hp": combat_state.current_hp.max_hp,
            "mp": combat_state.current_mp.value,
            "max_mp": combat_state.current_mp.max_mp,
            "attack": combat_state.attack,
            "defense": combat_state.defense,
            "speed": combat_state.speed,
            "level": 1,  # TODO: レベル情報を追加する必要がある場合
        }

        # TurnEndResultから情報を取得
        if turn_end_result:
            damage_from_status_effects = turn_end_result.damage
            healing_from_status_effects = turn_end_result.healing
            expired_status_effects = turn_end_result.status_effects_to_remove
            expired_buffs = turn_end_result.buffs_to_remove
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
            actor_id=entity_id,
            participant_type=participant_type,
            is_actor_defeated=not combat_state.is_alive(),
            damage_from_status_effects=damage_from_status_effects,
            healing_from_status_effects=healing_from_status_effects,
            expired_status_effects=expired_status_effects,
            expired_buffs=expired_buffs,
            final_actor_stats=final_actor_stats,
            messages=messages,
        ))
    
    def _advance_to_next_round(self) -> bool:
        """次のラウンドに進む"""
        # ラウンド終了イベントを発行
        self._emit_round_ended_event()
        
        self._current_round += 1
        self._current_turn_index = 0
        
        # ターン順序を再計算
        self._turn_order = self._turn_order_service.recalculate_turn_order_for_next_round(
            self._combat_states, self._turn_order
        )
        
        # 新しいラウンド開始イベントを発行
        if self._current_round <= self._max_rounds and len(self._turn_order) > 0:
            self._emit_round_started_event()
        
        return self._current_round <= self._max_rounds and len(self._turn_order) > 0
    
    def _emit_round_ended_event(self):
        """ラウンド終了イベントを発行"""
        round_summary = {
            "round_number": self._current_round,
            "total_turns_in_round": len(self._turn_order),
            "remaining_participants": len([entry for entry in self._turn_order
                                        if self._combat_states.get(entry.participant_key, None) and
                                        self._combat_states[entry.participant_key].is_alive()]),
        }

        next_round_turn_order = [(entry.participant_key[0], entry.participant_key[1]) for entry in self._turn_order]

        self.add_event(RoundEndedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            round_number=self._current_round,
            round_summary=round_summary,
            next_round_turn_order=next_round_turn_order,
        ))
    
    def join_player(self, player: Player, join_turn: int):  # TODO: モンスターにも対応
        """プレイヤーが戦闘に参加"""
        self._add_player(player)

        # プレイヤー参加イベント発行
        player_stats = {
            "entity_id": player.player_id,
            "name": player.name,
            "hp": player.hp.value,
            "max_hp": player.hp.max_hp,
            "mp": player.mp.value,
            "max_mp": player.mp.max_mp,
            "level": getattr(player, 'level', 1),
        }

        self.add_event(PlayerJoinedBattleEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            player_id=player.player_id,
            join_turn=join_turn,
            player_stats=player_stats,
        ))
    
    def join_monster(self, monster: Monster, join_turn: int):  # TODO: プレイヤーにも対応
        """モンスターが戦闘に参加"""
        self._add_monster(monster)

        # モンスター参加イベント発行
        monster_stats = {
            "entity_id": self._monster_count_for_identification,  # 最新のモンスターIDを使用
            "name": monster.name,
            "hp": monster.max_hp,
            "max_hp": monster.max_hp,
            "mp": monster.max_mp,
            "max_mp": monster.max_mp,
            "level": 1,  # TODO: モンスターのレベル情報を追加する必要がある場合
        }

        self.add_event(MonsterJoinedBattleEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            monster_id=self._monster_count_for_identification,
            join_turn=join_turn,
            monster_stats=monster_stats,
        ))

    def player_escape(self, player: Player):  # TODO: モンスターにも対応
        """プレイヤーが戦闘から離脱"""
        if player.player_id not in self._player_ids:
            raise ValueError("Player not in battle")  # TODO: カスタム例外を実装

        self._combat_states.pop((ParticipantType.PLAYER, player.player_id))
        self._player_ids.remove(player.player_id)
        self._escaped_player_ids.add(player.player_id)

        contribution_score = self._contribution_scores.get(player.player_id, 0)

        # プレイヤー離脱イベント発行
        final_stats = {
            "entity_id": player.player_id,
            "name": player.name,
            "hp": player.hp.value,
            "max_hp": player.hp.max_hp,
            "mp": player.mp.value,
            "max_mp": player.mp.max_mp,
            "level": getattr(player, 'level', 1),
        }

        self.add_event(PlayerLeftBattleEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            player_id=player.player_id,
            reason="escape",
            final_stats=final_stats,
            contribution_score=contribution_score,
        ))
        
    def apply_turn_start_result(self, turn_start_result: TurnStartResult):
        """ターン開始結果を適用"""
        combat_state = self._combat_states.get((turn_start_result.participant_type, turn_start_result.actor_id))
        if not combat_state:
            raise ValueError("Combat state not found")  # TODO: カスタム例外を実装
        
        combat_state = turn_start_result.apply_to_combat_state(combat_state)
        
        self._combat_states[(turn_start_result.participant_type, turn_start_result.actor_id)] = combat_state
    
    def apply_battle_action_result(self, battle_action_result: BattleActionResult):
        """アクション実行結果を適用"""
        combat_state = self._combat_states.get((battle_action_result.actor_state_change.participant_type, battle_action_result.actor_state_change.actor_id))
        if not combat_state:
            raise ValueError("Combat state not found")  # TODO: カスタム例外を実装
        combat_state = battle_action_result.actor_state_change.apply_to_combat_state(combat_state)
        self._combat_states[(battle_action_result.actor_state_change.participant_type, battle_action_result.actor_state_change.actor_id)] = combat_state

        for target_state_change in battle_action_result.target_state_changes:
            target_combat_state = self._combat_states.get((target_state_change.participant_type, target_state_change.target_id))
            if not target_combat_state:
                raise ValueError("Combat state not found")  # TODO: カスタム例外を実装
            
            target_combat_state = target_state_change.apply_to_combat_state(target_combat_state)
            
            self._combat_states[(target_state_change.participant_type, target_state_change.target_id)] = target_combat_state
        
        self._combat_states[(battle_action_result.actor_state_change.participant_type, battle_action_result.actor_state_change.actor_id)] = combat_state
    
    def apply_turn_end_result(self, turn_end_result: TurnEndResult):
        """ターン終了結果を適用"""
        combat_state = self._combat_states.get((turn_end_result.participant_type, turn_end_result.actor_id))
        if not combat_state:
            raise ValueError("Combat state not found")  # TODO: カスタム例外を実装
        
        combat_state = turn_end_result.apply_to_combat_state(combat_state)
        combat_state = combat_state.with_turn_progression()  # 状態異常とバフの残りターン数を減らす
        
        self._combat_states[(turn_end_result.participant_type, turn_end_result.actor_id)] = combat_state
    
    def check_battle_end_conditions(self) -> Optional[BattleResultType]:
        """戦闘終了条件をチェック（IDベース）"""
        # プレイヤー全滅チェック
        alive_player_ids = [
            participant.entity_id
            for participant in self._combat_states.values()
            if participant.participant_type == ParticipantType.PLAYER and participant.is_alive()
        ]
        if len(alive_player_ids) == 0:
            return BattleResultType.DEFEAT

        # モンスター全滅チェック
        alive_monster_ids = [
            participant.entity_id
            for participant in self._combat_states.values()
            if participant.participant_type == ParticipantType.MONSTER and participant.is_alive()
        ]
        if len(alive_monster_ids) == 0:
            return BattleResultType.VICTORY

        # 最大ターン数チェック
        if self._current_round >= self._max_rounds:
            return BattleResultType.DRAW

        return None

    def remove_defeated_participant(self, participant_type: ParticipantType, entity_id: int, defeated_by_participant_type: ParticipantType, defeated_by_entity_id: int):
        """撃破された参加者を削除"""
        combat_state = self._combat_states.get((participant_type, entity_id))
        if not combat_state or combat_state.is_alive():
            return

        final_stats = {
            "entity_id": combat_state.entity_id,
            "name": combat_state.name,
            "hp": combat_state.current_hp.value,
            "max_hp": combat_state.current_hp.max_hp,
            "mp": combat_state.current_mp.value,
            "max_mp": combat_state.current_mp.max_mp,
            "level": 1,  # TODO: レベル情報を追加する必要がある場合
        }

        if participant_type == ParticipantType.PLAYER:
            if entity_id in self._player_ids:
                self._player_ids.remove(entity_id)
                self.add_event(PlayerDefeatedEvent.create(
                    aggregate_id=self._battle_id,
                    aggregate_type="battle",
                    battle_id=self._battle_id,
                    player_id=entity_id,
                    defeated_by_monster_id=defeated_by_entity_id if defeated_by_participant_type == ParticipantType.MONSTER else 0,
                    defeat_turn=self._current_turn,
                    defeat_round=self._current_round,
                    final_player_stats=final_stats,
                    damage_dealt_by_defeater=0,  # TODO: 撃破者のダメージ情報を計算
                ))
        elif participant_type == ParticipantType.MONSTER:
            if entity_id in self._monster_ids:
                self._monster_ids.remove(entity_id)
                # ドロップ報酬の計算
                drop_reward = {}
                # モンスターのドロップ報酬は別途計算（CombatStateには元のエンティティ情報がない）
                # 実際の実装では、MonsterRepositoryから取得するか、CombatStateに保持する
                drop_reward = {"gold": 50, "exp": 25}  # 簡易実装

                self.add_event(MonsterDefeatedEvent.create(
                    aggregate_id=self._battle_id,
                    aggregate_type="battle",
                    battle_id=self._battle_id,
                    monster_id=entity_id,
                    monster_type_id=0,  # 簡易実装: 実際の実装では別途取得
                    defeated_by_player_id=defeated_by_entity_id if defeated_by_participant_type == ParticipantType.PLAYER else 0,
                    defeat_turn=self._current_turn,
                    defeat_round=self._current_round,
                    drop_reward=drop_reward,
                    final_monster_stats=final_stats,
                    damage_dealt_by_defeater=0,  # TODO: 撃破者のダメージ情報を計算
                ))

        # 戦闘状態から削除
        self._combat_states.pop((participant_type, entity_id))

    def execute_turn(self, actor_participant_type: ParticipantType, actor_entity_id: int, action_result: BattleActionResult):
        """ターンを執行"""
        # 現在のアクターが正しいかチェック
        current_actor = self.get_current_actor()
        if not current_actor or current_actor.participant_key != (actor_participant_type, actor_entity_id):
            raise ValueError(f"Invalid actor: expected {(current_actor.participant_key if current_actor else None)}, got {(actor_participant_type, actor_entity_id)}")

        # ターン実行イベント発行
        self.add_event(TurnExecutedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            turn_number=self._current_turn,
            round_number=self._current_round,
            actor_id=actor_entity_id,
            participant_type=actor_participant_type,
            action_type="",  # TODO: アクションタイプ情報の追加
            action_name="",  # TODO: アクション名情報の追加
            target_ids=[change.target_id for change in action_result.target_state_changes],
            target_participant_types=[change.participant_type for change in action_result.target_state_changes],
            damage_dealt=action_result.total_damage_dealt,
            healing_done=action_result.total_healing_dealt,
            hp_consumed=0,  # TODO: HP消費情報の追加
            mp_consumed=0,  # TODO: MP消費情報の追加
            critical_hits=action_result.metadata.critical_hits if action_result.metadata else [],
            compatibility_multipliers=action_result.metadata.compatibility_multipliers if action_result.metadata else [],
            applied_status_effects=[],  # TODO: アクション結果から取得
            applied_buffs=[],  # TODO: アクション結果から取得
            messages=action_result.messages,
            success=action_result.success,
            failure_reason=action_result.failure_reason,
        ))

        # 状態異常・バフ適用イベントの発行
        self._emit_status_effect_events(action_result, actor_entity_id, actor_participant_type)
        self._emit_buff_events(action_result, actor_entity_id, actor_participant_type)

    def _emit_status_effect_events(self, action_result: BattleActionResult, actor_id: int, actor_type: ParticipantType):
        """状態異常関連イベントを発行"""
        for target_change in action_result.target_state_changes:
            for effect_type, duration in target_change.status_effects_to_add:
                self.add_event(StatusEffectAppliedEvent.create(
                    aggregate_id=self._battle_id,
                    aggregate_type="battle",
                    battle_id=self._battle_id,
                    target_id=target_change.target_id,
                    participant_type=target_change.participant_type,
                    status_effect_type=effect_type,
                    duration=duration,
                    applied_turn=self._current_turn,
                    applied_round=self._current_round,
                    applied_by_id=actor_id,
                    applied_by_type=actor_type,
                ))

    def _emit_buff_events(self, action_result: BattleActionResult, actor_id: int, actor_type: ParticipantType):
        """バフ関連イベントを発行"""
        for target_change in action_result.target_state_changes:
            for buff_type, multiplier, duration in target_change.buffs_to_add:
                self.add_event(BuffAppliedEvent.create(
                    aggregate_id=self._battle_id,
                    aggregate_type="battle",
                    battle_id=self._battle_id,
                    target_id=target_change.target_id,
                    participant_type=target_change.participant_type,
                    buff_type=buff_type,
                    multiplier=multiplier,
                    duration=duration,
                    applied_turn=self._current_turn,
                    applied_round=self._current_round,
                    applied_by_id=actor_id,
                    applied_by_type=actor_type,
                ))

    def end_battle(self, result_type: BattleResultType):
        """戦闘を終了"""
        self._state = BattleState.COMPLETED

        # 勝利時のドロップ報酬計算
        drop_rewards = {}
        total_rewards = {"gold": 0, "exp": 0}
        if result_type == BattleResultType.VICTORY:
            drop_rewards = EMPTY_REWARD
            for monster_id in self._monster_ids:
                monster_state = self._combat_states.get((ParticipantType.MONSTER, monster_id))
                if monster_state and not monster_state.is_alive():
                    # 簡易実装: 実際の実装では MonsterRepository から取得
                    from src.domain.monster.drop_reward import DropReward
                    from src.domain.common.value_object import Gold, Exp
                    monster_drop = DropReward(gold=Gold(50), exp=Exp(25))
                    drop_rewards += monster_drop

            # 報酬の計算（簡易版）
            total_rewards = {"gold": 1000, "exp": 500}  # TODO: 実際の報酬計算ロジックを実装

        # 勝者IDの取得
        winner_ids = []
        if result_type == BattleResultType.VICTORY:
            winner_ids = list(self._player_ids)  # 生存プレイヤーが勝者

        # 戦闘終了イベント発行
        self.add_event(BattleEndedEvent.create(
            aggregate_id=self._battle_id,
            aggregate_type="battle",
            battle_id=self._battle_id,
            spot_id=self._spot_id,
            result_type=result_type,
            winner_ids=winner_ids,
            participant_ids=list(self._player_ids),
            total_turns=self._current_turn,
            total_rounds=self._current_round,
            total_rewards=total_rewards,
            battle_statistics={},  # TODO: 戦闘統計を実装する場合
            contribution_scores=self._contribution_scores,
        ))
        


# class _Battle(AggregateRoot):
#     """戦闘の集約ルート"""
    
#     def __init__(
#         self,
#         battle_id: int,
#         spot_id: int,
#         initiating_player_id: int,
#         monster_ids: List[int],
#         max_players: int = 4,
#         max_turns: int = 30,
#     ):
#         super().__init__()
#         self._battle_id = battle_id
#         self._spot_id = spot_id
#         self._participant_player_ids: List[int] = [initiating_player_id]
#         self._monster_ids: List[int] = monster_ids
#         self._max_players = max_players
#         self._max_turns = max_turns
#         self._state = BattleState.WAITING
        
#         # ==== ターン管理 ====
#         self._turn_order_service = TurnOrderService()
#         self._turn_order: List[TurnEntry] = []
#         self._turn_history: List[TurnRecord] = []
#         self._current_turn = 0
#         self._current_round = 0
#         self._current_turn_index = 0
        
#         # ==== 戦闘結果管理 ====
#         self._total_damage_dealt: Dict[Tuple[ParticipantType, int], int] = {}  # (participant_type, entity_id) -> total_damage
#         self._total_healing_done: Dict[Tuple[ParticipantType, int], int] = {}  # (participant_type, entity_id) -> total_healing
#         self._contribution_scores: Dict[int, int] = {}  # player_id -> contribution
#         self._battle_statistics: Dict[str, Any] = {
#             "total_damage_dealt": 0,
#             "total_healing_done": 0,
#             "total_critical_hits": 0,
#             "total_status_effects_applied": 0,
#             "total_buffs_applied": 0,
#         }
        
#         # ==== 逃走管理 ====
#         self._escaped_player_ids: Set[int] = set()
#         self._escaped_monster_ids: Set[int] = set()
        
#     def get_current_actor(self) -> TurnEntry:
#         """現在のターンのアクター取得"""
#         if not self._turn_order:
#             raise ValueError("Turn order not calculated")
        
#         return self._turn_order[self._current_turn_index]
    
#     def get_next_actor(self) -> Optional[TurnEntry]:
#         """次のアクター取得"""
#         return self._turn_order_service.get_next_actor(self._turn_order, self._current_turn_index)

#     def start_battle(self, all_participants: Dict[int, CombatEntity]):
#         """戦闘開始"""
#         self._state = BattleState.IN_PROGRESS
        
#         # ターン順序を計算
#         self._turn_order = self._turn_order_service.calculate_initial_turn_order(all_participants)
#         self._current_turn_index = 0
#         self._current_round = 1
        
#         # 戦闘開始イベント発行
#         self.add_event(BattleStartedEvent.create(
#             aggregate_id=self._battle_id,
#             aggregate_type="battle",
#             battle_id=self._battle_id,
#             spot_id=self._spot_id,
#             player_ids=self._participant_player_ids,
#             monster_ids=self._monster_ids,
#             max_players=self._max_players,
#             max_turns=self._max_turns,
#             battle_config={
#                 "max_players": self._max_players,
#                 "max_turns": self._max_turns,
#                 "initial_participants": len(all_participants),
#             }
#         ))
        
#         # ラウンド開始イベント発行
#         self._emit_round_started_event(all_participants)

#     def _emit_round_started_event(self, all_participants: Dict[int, CombatEntity]):
#         """ラウンド開始イベントを発行"""
#         turn_order_data = [(entry.entity_id, entry.participant_type) for entry in self._turn_order]
#         remaining_participants = {
#             ParticipantType.PLAYER: [pid for pid in self._participant_player_ids if pid in all_participants],
#             ParticipantType.MONSTER: [mid for mid in self._monster_ids if mid in all_participants],
#         }
        
#         round_stats = {
#             "total_participants": len(self._turn_order),
#             "player_count": len(remaining_participants[ParticipantType.PLAYER]),
#             "monster_count": len(remaining_participants[ParticipantType.MONSTER]),
#         }
        
#         self.add_event(RoundStartedEvent.create(
#             aggregate_id=self._battle_id,
#             aggregate_type="battle",
#             battle_id=self._battle_id,
#             round_number=self._current_round,
#             turn_order=turn_order_data,
#             remaining_participants=remaining_participants,
#             round_stats=round_stats,
#         ))

#     def start_turn(self, actor: CombatEntity, participant_type: ParticipantType) -> None:
#         """ターン開始処理"""
#         can_act = True
#         status_effects = []
#         active_buffs = []
#         messages = []
        
#         # アクターの統計情報を取得
#         actor_stats = self._get_entity_stats(actor)
        
#         # ターン開始イベントを発行
#         self.add_event(TurnStartedEvent.create(
#             aggregate_id=self._battle_id,
#             aggregate_type="battle",
#             battle_id=self._battle_id,
#             turn_number=self._current_turn,
#             round_number=self._current_round,
#             actor_id=actor.entity_id,
#             participant_type=participant_type,
#             actor_stats=actor_stats,
#             can_act=can_act,
#             status_effects=status_effects,
#             active_buffs=active_buffs,
#             messages=messages,
#         ))

#     def _get_entity_stats(self, entity: CombatEntity) -> Dict[str, Any]:
#         """エンティティの統計情報を取得"""
#         return {
#             "entity_id": entity.entity_id,
#             "name": entity.name,
#             "hp": entity.hp,
#             "max_hp": entity.max_hp,
#             "mp": entity.mp,
#             "max_mp": entity.max_mp,
#             "attack": entity.attack,
#             "defense": entity.defense,
#             "speed": entity.speed,
#             "level": getattr(entity, 'level', 1),
#         }

#     def advance_to_next_turn(self, all_participants: Dict[int, CombatEntity], turn_end_result: Optional[TurnEndResult] = None) -> bool:
#         """次のターンに進む"""
#         # 現在のターン終了イベントを発行
#         current_actor = self.get_current_actor()
#         if current_actor:
#             self._emit_turn_ended_event(current_actor, all_participants, turn_end_result)
        
#         self._current_turn_index += 1
        
#         # ラウンド終了チェック
#         if self._current_turn_index >= len(self._turn_order):
#             return self._advance_to_next_round(all_participants)
        
#         return True
    
#     def _emit_turn_ended_event(self, actor_entry: TurnEntry, all_participants: Dict[int, CombatEntity], turn_end_result: Optional[TurnEndResult] = None):
#         """ターン終了イベントを発行"""
#         actor = all_participants.get(actor_entry.entity_id)
#         if not actor:
#             return
            
#         actor_stats = self._get_entity_stats(actor)
        
#         # TurnEndResultから情報を取得（ない場合はデフォルト値）
#         if turn_end_result:
#             damage_from_status_effects = turn_end_result.damage_from_status_effects
#             healing_from_status_effects = turn_end_result.healing_from_status_effects
#             expired_status_effects = turn_end_result.expired_status_effects
#             expired_buffs = turn_end_result.expired_buffs
#             messages = turn_end_result.messages
#         else:
#             damage_from_status_effects = 0
#             healing_from_status_effects = 0
#             expired_status_effects = []
#             expired_buffs = []
#             messages = []
        
#         self.add_event(TurnEndedEvent.create(
#             aggregate_id=self._battle_id,
#             aggregate_type="battle",
#             battle_id=self._battle_id,
#             turn_number=self._current_turn,
#             round_number=self._current_round,
#             actor_id=actor_entry.entity_id,
#             participant_type=actor_entry.participant_type,
#             is_actor_defeated=not actor.is_alive(),
#             damage_from_status_effects=damage_from_status_effects,
#             healing_from_status_effects=healing_from_status_effects,
#             expired_status_effects=expired_status_effects,
#             expired_buffs=expired_buffs,
#             final_actor_stats=actor_stats,
#             messages=messages,
#         ))
    
#     def _advance_to_next_round(self, all_participants: Dict[int, CombatEntity]) -> bool:
#         """次のラウンドに進む"""
#         # ラウンド終了イベントを発行
#         self._emit_round_ended_event(all_participants)
        
#         self._current_round += 1
#         self._current_turn_index = 0
        
#         # ターン順序を再計算
#         self._turn_order = self._turn_order_service.recalculate_turn_order_for_next_round(
#             all_participants, self._turn_order
#         )
        
#         # 新しいラウンド開始イベントを発行
#         if self._current_round <= self._max_turns and len(self._turn_order) > 0:
#             self._emit_round_started_event(all_participants)
        
#         return self._current_round <= self._max_turns and len(self._turn_order) > 0
    
#     def _emit_round_ended_event(self, all_participants: Dict[int, CombatEntity]):
#         """ラウンド終了イベントを発行"""
#         round_summary = {
#             "round_number": self._current_round,
#             "total_turns_in_round": len(self._turn_order),
#             "remaining_participants": len(self._turn_order),
#         }
        
#         next_round_turn_order = [(entry.entity_id, entry.participant_type) for entry in self._turn_order]
        
#         self.add_event(RoundEndedEvent.create(
#             aggregate_id=self._battle_id,
#             aggregate_type="battle",
#             battle_id=self._battle_id,
#             round_number=self._current_round,
#             round_summary=round_summary,
#             next_round_turn_order=next_round_turn_order,
#         ))
    
#     def join_player(self, player_id: int, player_stats: Dict[str, Any]) -> bool:
#         """プレイヤーが戦闘に参加"""
#         if len(self._participant_player_ids) >= self._max_players:
#             return False

#         if player_id in self._participant_player_ids:
#             return False
        
#         self._participant_player_ids.append(player_id)
#         self.add_event(PlayerJoinedBattleEvent.create(
#             aggregate_id=self._battle_id,
#             aggregate_type="battle",
#             battle_id=self._battle_id,
#             player_id=player_id,
#             join_turn=self._current_turn,
#             player_stats=player_stats,
#         ))
#         return True
    
#     def player_escape(self, player_id: int, final_stats: Dict[str, Any]) -> bool:
#         """プレイヤーが戦闘から離脱"""
#         if player_id not in self._participant_player_ids:
#             return False
        
#         self._participant_player_ids.remove(player_id)
#         self._escaped_player_ids.add(player_id)
        
#         contribution_score = self._contribution_scores.get(player_id, 0)

#         self.add_event(PlayerLeftBattleEvent.create(
#             aggregate_id=self._battle_id,
#             aggregate_type="battle",
#             battle_id=self._battle_id,
#             player_id=player_id,
#             reason="escape",
#             final_stats=final_stats,
#             contribution_score=contribution_score,
#         ))
#         return True

#     def execute_turn(
#         self,
#         actor_id: int,
#         participant_type: ParticipantType,
#         action_type: str,
#         action_name: str,
#         target_ids: List[int],
#         target_participant_types: List[ParticipantType],
#         battle_action_result: BattleActionResult
#     ) -> None:
#         """ターンを実行"""
#         actor = self.get_current_actor()
#         if actor.entity_id != actor_id or actor.participant_type != participant_type:
#             raise ValueError(f"Invalid actor: {actor_id}, {participant_type}, {actor.entity_id}, {actor.participant_type}")
        
#         # 統計情報を更新
#         key = (participant_type, actor_id)
#         self._total_damage_dealt[key] = self._total_damage_dealt.get(key, 0) + battle_action_result.total_damage
#         self._total_healing_done[key] = self._total_healing_done.get(key, 0) + battle_action_result.total_healing
        
#         # 戦闘統計を更新
#         self._battle_statistics["total_damage_dealt"] += battle_action_result.total_damage
#         self._battle_statistics["total_healing_done"] += battle_action_result.total_healing
#         self._battle_statistics["total_critical_hits"] += sum(battle_action_result.critical_hits)
#         self._battle_statistics["total_status_effects_applied"] += len(battle_action_result.applied_status_effects)
#         self._battle_statistics["total_buffs_applied"] += len(battle_action_result.applied_buffs)
        
#         # ターン実行イベントを発行
#         self.add_event(TurnExecutedEvent.create(
#             aggregate_id=self._battle_id,
#             aggregate_type="battle",
#             battle_id=self._battle_id,
#             turn_number=self._current_turn,
#             round_number=self._current_round,
#             actor_id=actor_id,
#             participant_type=participant_type,
#             action_type=action_type,
#             action_name=action_name,
#             target_ids=target_ids,
#             target_participant_types=target_participant_types,
#             damage_dealt=battle_action_result.total_damage,
#             healing_done=battle_action_result.total_healing,
#             hp_consumed=battle_action_result.hp_consumed,
#             mp_consumed=battle_action_result.mp_consumed,
#             critical_hits=battle_action_result.critical_hits,
#             compatibility_multipliers=battle_action_result.compatibility_multipliers,
#             applied_status_effects=battle_action_result.applied_status_effects,
#             applied_buffs=battle_action_result.applied_buffs,
#             messages=battle_action_result.messages,
#             success=battle_action_result.success,
#             failure_reason=battle_action_result.failure_reason,
#         ))
        
#         # 状態異常・バフ適用イベントを発行
#         self._emit_status_effect_events(battle_action_result, actor_id, participant_type)
#         self._emit_buff_events(battle_action_result, actor_id, participant_type)
    
#     def _emit_status_effect_events(self, battle_action_result: BattleActionResult, actor_id: int, actor_type: ParticipantType):
#         """状態異常関連イベントを発行"""
#         for target_id, status_effect_type, duration in battle_action_result.applied_status_effects:
#             self.add_event(StatusEffectAppliedEvent.create(
#                 aggregate_id=self._battle_id,
#                 aggregate_type="battle",
#                 battle_id=self._battle_id,
#                 target_id=target_id,
#                 participant_type=ParticipantType.PLAYER if target_id in self._participant_player_ids else ParticipantType.MONSTER,
#                 status_effect_type=status_effect_type,
#                 duration=duration,
#                 applied_turn=self._current_turn,
#                 applied_round=self._current_round,
#                 applied_by_id=actor_id,
#                 applied_by_type=actor_type,
#             ))
    
#     def _emit_buff_events(self, battle_action_result: BattleActionResult, actor_id: int, actor_type: ParticipantType):
#         """バフ関連イベントを発行"""
#         for target_id, buff_type, multiplier, duration in battle_action_result.applied_buffs:
#             self.add_event(BuffAppliedEvent.create(
#                 aggregate_id=self._battle_id,
#                 aggregate_type="battle",
#                 battle_id=self._battle_id,
#                 target_id=target_id,
#                 participant_type=ParticipantType.PLAYER if target_id in self._participant_player_ids else ParticipantType.MONSTER,
#                 buff_type=buff_type,
#                 multiplier=multiplier,
#                 duration=duration,
#                 applied_turn=self._current_turn,
#                 applied_round=self._current_round,
#                 applied_by_id=actor_id,
#                 applied_by_type=actor_type,
#             ))
    
#     def check_battle_end_conditions(self) -> Optional[BattleResultType]:
#         """戦闘終了条件をチェック（IDベース）"""
#         # プレイヤー全滅チェック
#         if len(self._participant_player_ids) == 0:
#             return BattleResultType.DEFEAT
        
#         # モンスター全滅チェック
#         if len(self._monster_ids) == 0:
#             return BattleResultType.VICTORY
        
#         # 最大ターン数チェック
#         if self._current_round >= self._max_turns:
#             return BattleResultType.DRAW
        
#         return None
    
#     def remove_defeated_participant(self, entity_id: int, entity_type: ParticipantType, final_stats: Dict[str, Any], defeated_by_id: int, defeated_by_type: ParticipantType):
#         """撃破された参加者を削除"""
#         if entity_type == ParticipantType.PLAYER:
#             if entity_id in self._participant_player_ids:
#                 self._participant_player_ids.remove(entity_id)
#                 self.add_event(PlayerDefeatedEvent.create(
#                     aggregate_id=self._battle_id,
#                     aggregate_type="battle",
#                     battle_id=self._battle_id,
#                     player_id=entity_id,
#                     defeated_by_monster_id=defeated_by_id,
#                     defeat_turn=self._current_turn,
#                     defeat_round=self._current_round,
#                     final_player_stats=final_stats,
#                     damage_dealt_by_defeater=0,  # BattleServiceから取得する必要がある
#                 ))
#         elif entity_type == ParticipantType.MONSTER:
#             if entity_id in self._monster_ids:
#                 self._monster_ids.remove(entity_id)
#                 self.add_event(MonsterDefeatedEvent.create(
#                     aggregate_id=self._battle_id,
#                     aggregate_type="battle",
#                     battle_id=self._battle_id,
#                     monster_id=entity_id,
#                     monster_type_id=0,  # モンスタータイプIDは別途取得する必要がある
#                     defeated_by_player_id=defeated_by_id,
#                     defeat_turn=self._current_turn,
#                     defeat_round=self._current_round,
#                     drop_reward={},  # ドロップ報酬は別途計算する必要がある
#                     final_monster_stats=final_stats,
#                     damage_dealt_by_defeater=0,  # BattleServiceから取得する必要がある
#                 ))

#     def end_battle(self, result_type: BattleResultType, winner_ids: List[int]) -> None:
#         """戦闘を終了"""
#         self._state = BattleState.COMPLETED
        
#         # 戦闘終了イベントを発行
#         self.add_event(BattleEndedEvent.create(
#             aggregate_id=self._battle_id,
#             aggregate_type="battle",
#             battle_id=self._battle_id,
#             spot_id=self._spot_id,
#             result_type=result_type,
#             winner_ids=winner_ids,
#             participant_ids=self._participant_player_ids,
#             total_turns=self._current_turn,
#             total_rounds=self._current_round,
#             total_rewards={"gold": 1000, "exp": 500},  # 計算ロジックは別途実装
#             battle_statistics=self._battle_statistics,
#             contribution_scores=self._contribution_scores,
#         ))
    
#     def update_contribution_score(self, player_id: int, score: int):
#         """プレイヤーの貢献度スコアを更新"""
#         self._contribution_scores[player_id] = self._contribution_scores.get(player_id, 0) + score