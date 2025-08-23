import pytest
from unittest.mock import Mock, MagicMock
from src.domain.battle.battle import Battle
from src.domain.battle.battle_service import BattleService
from src.domain.battle.battle_enum import BattleState, BattleResultType, ParticipantType, StatusEffectType, BuffType
from src.domain.battle.combat_entity import CombatEntity
from src.domain.battle.battle_result import BattleActionResult
from src.domain.player.player import Player
from src.domain.monster.monster import Monster
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.conversation.message_box import MessageBox
from src.domain.player.player_enum import Role, PlayerState
from src.domain.monster.monster_enum import Race
from src.domain.battle.battle_enum import Element
from src.domain.monster.drop_reward import DropReward
from src.domain.battle.battle_action import BattleAction
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.domain.player.exp import Exp
from src.domain.player.level import Level
from src.domain.player.gold import Gold


class TestBattleEvents:
    """Battleクラスのイベント機能テスト"""
    
    def setup_method(self):
        """テスト前の準備"""
        self.battle = Battle(
            battle_id=1,
            spot_id=100,
            initiating_player_id=1,
            monster_ids=[101, 102],
            max_players=4,
            max_turns=30,
        )
        self.battle_service = BattleService()
        
        # 実際のPlayerオブジェクトを作成
        base_status = BaseStatus(
            attack=20,
            defense=10,
            speed=15,
            critical_rate=0.1,
            evasion_rate=0.05,
        )
        dynamic_status = DynamicStatus(
            hp=Hp(value=100, max_hp=100),
            mp=Mp(value=50, max_mp=50),
            exp=Exp(value=1000, max_exp=1000),
            level=Level(value=5),
            gold=Gold(value=500),
        )
        inventory = Inventory.create_empty(20)
        equipment_set = EquipmentSet()
        message_box = MessageBox()
        
        self.player = Player(
            player_id=1,
            name="テストプレイヤー",
            role=Role.ADVENTURER,
            current_spot_id=100,
            base_status=base_status,
            dynamic_status=dynamic_status,
            inventory=inventory,
            equipment_set=equipment_set,
            message_box=message_box,
        )
        
        # 実際のMonsterオブジェクトを作成
        monster_base_status = BaseStatus(
            attack=25,
            defense=8,
            speed=12,
            critical_rate=0.05,
            evasion_rate=0.1,
        )
        monster_dynamic_status = DynamicStatus(
            hp=Hp(value=80, max_hp=80),
            mp=Mp(value=30, max_mp=30),
            exp=Exp(value=0, max_exp=0),
            level=Level(value=3),
            gold=Gold(value=0),
        )
        drop_reward = DropReward(gold=100, exp=50, items=[])
        available_actions = []
        
        self.monster = Monster(
            monster_instance_id=101,
            monster_type_id=1,
            name="テストモンスター",
            description="テスト用のモンスター",
            race=Race.GOBLIN,
            element=Element.FIRE,
            current_spot_id=100,
            base_status=monster_base_status,
            dynamic_status=monster_dynamic_status,
            available_actions=available_actions,
            drop_reward=drop_reward,
            allowed_areas=[100],
        )
        
        self.all_participants = {
            1: self.player,
            101: self.monster,
        }
    
    def test_battle_started_event(self):
        """戦闘開始イベントのテスト"""
        # 戦闘開始
        self.battle.start_battle(self.all_participants)
        
        # イベントが発行されているかチェック
        events = self.battle.get_events()
        assert len(events) >= 2  # BattleStartedEvent + RoundStartedEvent
        
        # BattleStartedEventを確認
        battle_started_event = next(e for e in events if e.__class__.__name__ == "BattleStartedEvent")
        assert battle_started_event.battle_id == 1
        assert battle_started_event.spot_id == 100
        assert battle_started_event.player_ids == [1]
        assert battle_started_event.monster_ids == [101, 102]
        assert battle_started_event.max_players == 4
        assert battle_started_event.max_turns == 30
        assert "max_players" in battle_started_event.battle_config
        assert "max_turns" in battle_started_event.battle_config
    
    def test_round_started_event(self):
        """ラウンド開始イベントのテスト"""
        self.battle.start_battle(self.all_participants)
        
        events = self.battle.get_events()
        round_started_event = next(e for e in events if e.__class__.__name__ == "RoundStartedEvent")
        
        assert round_started_event.battle_id == 1
        assert round_started_event.round_number == 1
        assert len(round_started_event.turn_order) > 0
        assert "total_participants" in round_started_event.round_stats
        assert "player_count" in round_started_event.round_stats
        assert "monster_count" in round_started_event.round_stats
    
    def test_turn_executed_event(self):
        """ターン実行イベントのテスト"""
        self.battle.start_battle(self.all_participants)
        
        # モックのBattleActionResultを作成
        mock_result = BattleActionResult.create_success(
            messages=["テスト攻撃"],
            target_ids=[101],
            damages=[30],
            healing_amounts=[0],
            is_target_defeated=[False],
            critical_hits=[True],
            compatibility_multipliers=[1.5],
        )
        
        # ターン実行
        self.battle.execute_turn(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            action_type="attack",
            action_name="通常攻撃",
            target_ids=[101],
            target_participant_types=[ParticipantType.MONSTER],
            battle_action_result=mock_result
        )
        
        events = self.battle.get_events()
        turn_executed_event = next(e for e in events if e.__class__.__name__ == "TurnExecutedEvent")
        
        assert turn_executed_event.battle_id == 1
        assert turn_executed_event.actor_id == 1
        assert turn_executed_event.participant_type == ParticipantType.PLAYER
        assert turn_executed_event.action_type == "attack"
        assert turn_executed_event.action_name == "通常攻撃"
        assert turn_executed_event.target_ids == [101]
        assert turn_executed_event.damage_dealt == 30
        assert turn_executed_event.success is True
        assert turn_executed_event.critical_hits == [True]
        assert turn_executed_event.compatibility_multipliers == [1.5]
    
    def test_player_joined_battle_event(self):
        """プレイヤー参加イベントのテスト"""
        player_stats = {
            "entity_id": 2,
            "name": "新規プレイヤー",
            "hp": 90,
            "max_hp": 90,
            "mp": 40,
            "max_mp": 40,
            "attack": 18,
            "defense": 12,
            "speed": 14,
            "level": 4,
        }
        
        success = self.battle.join_player(2, player_stats)
        assert success is True
        
        events = self.battle.get_events()
        player_joined_event = next(e for e in events if e.__class__.__name__ == "PlayerJoinedBattleEvent")
        
        assert player_joined_event.battle_id == 1
        assert player_joined_event.player_id == 2
        assert player_joined_event.join_turn == 0
        assert player_joined_event.player_stats == player_stats
    
    def test_player_escape_event(self):
        """プレイヤー逃走イベントのテスト"""
        final_stats = {
            "entity_id": 1,
            "name": "テストプレイヤー",
            "hp": 50,
            "max_hp": 100,
            "mp": 20,
            "max_mp": 50,
            "attack": 20,
            "defense": 10,
            "speed": 15,
            "level": 5,
        }
        
        success = self.battle.player_escape(1, final_stats)
        assert success is True
        
        events = self.battle.get_events()
        player_left_event = next(e for e in events if e.__class__.__name__ == "PlayerLeftBattleEvent")
        
        assert player_left_event.battle_id == 1
        assert player_left_event.player_id == 1
        assert player_left_event.reason == "escape"
        assert player_left_event.final_stats == final_stats
        assert player_left_event.contribution_score == 0
    
    def test_battle_statistics_update(self):
        """戦闘統計の更新テスト"""
        self.battle.start_battle(self.all_participants)
        
        # 複数のターンを実行して統計を更新
        mock_result1 = BattleActionResult.create_success(
            messages=["攻撃1"],
            target_ids=[101],
            damages=[25],
            healing_amounts=[0],
            is_target_defeated=[False],
            critical_hits=[True],
            compatibility_multipliers=[1.0],
        )
        
        mock_result2 = BattleActionResult.create_success(
            messages=["攻撃2"],
            target_ids=[101],
            damages=[30],
            healing_amounts=[0],
            is_target_defeated=[False],
            critical_hits=[False],
            compatibility_multipliers=[1.2],
        )
        
        self.battle.execute_turn(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            action_type="attack",
            action_name="通常攻撃1",
            target_ids=[101],
            target_participant_types=[ParticipantType.MONSTER],
            battle_action_result=mock_result1
        )
        
        self.battle.execute_turn(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            action_type="attack",
            action_name="通常攻撃2",
            target_ids=[101],
            target_participant_types=[ParticipantType.MONSTER],
            battle_action_result=mock_result2
        )
        
        # 統計が正しく更新されているかチェック
        assert self.battle._battle_statistics["total_damage_dealt"] == 55
        assert self.battle._battle_statistics["total_critical_hits"] == 1
        assert self.battle._battle_statistics["total_healing_done"] == 0
    
    def test_contribution_score_update(self):
        """貢献度スコアの更新テスト"""
        self.battle.update_contribution_score(1, 100)
        self.battle.update_contribution_score(1, 50)
        
        assert self.battle._contribution_scores[1] == 150
        
        # 別のプレイヤーのスコアも更新
        self.battle.update_contribution_score(2, 75)
        assert self.battle._contribution_scores[2] == 75
    
    def test_battle_service_entity_stats(self):
        """BattleServiceのエンティティ統計取得テスト"""
        # モックのBattleParticipantを作成
        mock_participant = Mock()
        mock_participant.entity = self.player
        mock_participant.get_status_effects.return_value = [StatusEffectType.POISON]
        mock_participant.buffs_remaining_duration = {BuffType.ATTACK: 3}
        
        stats = self.battle_service.get_entity_stats(mock_participant)
        
        assert stats["entity_id"] == 1
        assert stats["name"] == "テストプレイヤー"
        assert stats["hp"] == 100
        assert stats["max_hp"] == 100
        assert stats["mp"] == 50
        assert stats["max_mp"] == 50
        assert stats["attack"] == 20
        assert stats["defense"] == 10
        assert stats["speed"] == 15
        assert stats["level"] == 5
        assert StatusEffectType.POISON.value in stats["status_effects"]
        assert BuffType.ATTACK.value in stats["active_buffs"]
    
    def test_contribution_score_calculation(self):
        """貢献度スコア計算のテスト"""
        score = self.battle_service.calculate_contribution_score(
            damage_dealt=100,
            healing_done=50,
            critical_hits=2,
            status_effects_applied=3
        )
        
        # 期待値: 100 + (50 * 2) + (2 * 10) + (3 * 5) = 100 + 100 + 20 + 15 = 235
        expected_score = 100 + (50 * 2) + (2 * 10) + (3 * 5)
        assert score == expected_score
