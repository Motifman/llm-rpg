import pytest
from unittest.mock import Mock, patch
from game.battle.battle_manager import Battle
from game.battle.contribution_data import PlayerContribution, DistributedReward
from game.monster.monster import Monster, MonsterDropReward
from game.player.player import Player
from game.item.item import Item
from game.enums import BattleState, TurnActionType, MonsterType, Race, Element


class TestContributionBasedRewards:
    """貢献度に基づく報酬分配機能のテスト"""
    
    def setup_method(self):
        """テスト前のセットアップ"""
        # モンスターを作成
        self.monster1 = Monster(
            monster_id="test_monster_1",
            name="テストモンスター1",
            description="テスト用モンスター1",
            monster_type=MonsterType.NORMAL,
            race=Race.MONSTER,
            element=Element.PHYSICAL,
            drop_reward=MonsterDropReward(
                items=[Item("test_item_1", "テストアイテム1", "テスト用アイテム1")],
                money=100,
                experience=50,
                information=["テスト情報1"]
            )
        )
        
        self.monster2 = Monster(
            monster_id="test_monster_2",
            name="テストモンスター2",
            description="テスト用モンスター2",
            monster_type=MonsterType.NORMAL,
            race=Race.MONSTER,
            element=Element.PHYSICAL,
            drop_reward=MonsterDropReward(
                items=[Item("test_item_2", "テストアイテム2", "テスト用アイテム2")],
                money=200,
                experience=100,
                information=["テスト情報2"]
            )
        )
        
        # プレイヤーを作成
        self.player1 = Mock(spec=Player)
        self.player1.player_id = "player1"
        self.player1.name = "プレイヤー1"
        self.player1.get_player_id.return_value = "player1"
        self.player1.get_name.return_value = "プレイヤー1"
        self.player1.is_alive.return_value = True
        self.player1.get_attack.return_value = 20
        self.player1.get_defense.return_value = 10
        self.player1.get_speed.return_value = 15
        self.player1.get_hp.return_value = 100
        self.player1.get_max_hp.return_value = 100
        self.player1.take_damage = Mock()
        self.player1.set_defending = Mock()
        self.player1.is_defending.return_value = False
        self.player1.has_status_condition.return_value = False
        self.player1.get_equipped_weapon.return_value = None
        self.player1.get_critical_rate.return_value = 0.05
        
        # equipment属性をMockで作成
        equipment_mock = Mock()
        equipment_mock.get_equipped_armors.return_value = []
        self.player1.equipment = equipment_mock
        
        self.player2 = Mock(spec=Player)
        self.player2.player_id = "player2"
        self.player2.name = "プレイヤー2"
        self.player2.get_player_id.return_value = "player2"
        self.player2.get_name.return_value = "プレイヤー2"
        self.player2.is_alive.return_value = True
        self.player2.get_attack.return_value = 15
        self.player2.get_defense.return_value = 15
        self.player2.get_speed.return_value = 10
        self.player2.get_hp.return_value = 80
        self.player2.get_max_hp.return_value = 80
        self.player2.take_damage = Mock()
        self.player2.set_defending = Mock()
        self.player2.is_defending.return_value = False
        self.player2.has_status_condition.return_value = False
        self.player2.get_equipped_weapon.return_value = None
        self.player2.get_critical_rate.return_value = 0.05
        
        # equipment属性をMockで作成
        equipment_mock2 = Mock()
        equipment_mock2.get_equipped_armors.return_value = []
        self.player2.equipment = equipment_mock2
        
        # 戦闘を作成
        self.battle = Battle("test_battle", "test_spot", [self.monster1, self.monster2])
    
    def test_player_contribution_initialization(self):
        """プレイヤー貢献度の初期化テスト"""
        self.battle.add_participant(self.player1)
        
        assert "player1" in self.battle.player_contributions
        contribution = self.battle.player_contributions["player1"]
        assert contribution.player_id == "player1"
        assert contribution.total_damage_dealt == 0
        assert contribution.total_damage_taken == 0
        assert contribution.turns_participated == 0
    
    def test_contribution_score_calculation(self):
        """貢献度スコア計算のテスト"""
        contribution = PlayerContribution(
            player_id="test_player",
            total_damage_dealt=100,
            critical_hits=2,
            counter_attacks=1,
            status_effects_applied=1,
            turns_participated=5,
            total_damage_taken=20
        )
        
        score = contribution.calculate_contribution_score()
        expected_score = 100 + (2 * 10) + (1 * 15) + (1 * 20) + (5 * 5) - (20 * 0.1)
        assert score == expected_score
    
    def test_reward_distribution_basic(self):
        """基本的な報酬分配テスト"""
        # プレイヤーを追加
        self.battle.add_participant(self.player1)
        self.battle.add_participant(self.player2)
        
        # 貢献度を手動で設定
        self.battle.player_contributions["player1"].total_damage_dealt = 100
        self.battle.player_contributions["player2"].total_damage_dealt = 50
        
        # モンスターを倒した状態にする
        self.monster1.take_damage(1000)  # 死亡させる
        self.monster2.take_damage(1000)  # 死亡させる
        
        # 報酬分配を計算
        total_rewards = self.battle._calculate_total_rewards([self.monster1, self.monster2])
        distributed_rewards = self.battle._calculate_contribution_based_rewards(total_rewards)
        
        # 結果を検証
        assert len(distributed_rewards) == 2
        assert "player1" in distributed_rewards
        assert "player2" in distributed_rewards
        
        # 貢献度に応じた分配を確認
        player1_reward = distributed_rewards["player1"]
        player2_reward = distributed_rewards["player2"]
        
        # 貢献度比率: player1 = 100/(100+50) = 0.67, player2 = 50/(100+50) = 0.33
        assert player1_reward.contribution_percentage > player2_reward.contribution_percentage
        assert player1_reward.money > player2_reward.money
        assert player1_reward.experience > player2_reward.experience
    
    def test_reward_distribution_with_items(self):
        """アイテム分配のテスト"""
        self.battle.add_participant(self.player1)
        self.battle.add_participant(self.player2)
        
        # 貢献度を設定
        self.battle.player_contributions["player1"].total_damage_dealt = 100
        self.battle.player_contributions["player2"].total_damage_dealt = 50
        
        # モンスターを倒す
        self.monster1.take_damage(1000)
        self.monster2.take_damage(1000)
        
        total_rewards = self.battle._calculate_total_rewards([self.monster1, self.monster2])
        distributed_rewards = self.battle._calculate_contribution_based_rewards(total_rewards)
        
        # アイテムが分配されていることを確認
        player1_reward = distributed_rewards["player1"]
        player2_reward = distributed_rewards["player2"]
        
        assert len(player1_reward.items) > 0
        assert len(player2_reward.items) > 0
        # 情報は全員に渡される
        assert len(player1_reward.information) == 2
        assert len(player2_reward.information) == 2
    
    def test_battle_result_with_distributed_rewards(self):
        """戦闘結果での分配報酬テスト"""
        self.battle.add_participant(self.player1)
        self.battle.add_participant(self.player2)
        
        # 貢献度を設定
        self.battle.player_contributions["player1"].total_damage_dealt = 100
        self.battle.player_contributions["player2"].total_damage_dealt = 50
        
        # モンスターを倒して戦闘を終了
        self.monster1.take_damage(1000)
        self.monster2.take_damage(1000)
        self.battle.state = BattleState.FINISHED
        
        # 戦闘結果を取得
        result = self.battle.get_battle_result()
        
        # 分配された報酬が含まれていることを確認
        assert result.victory is True
        assert len(result.distributed_rewards) == 2
        assert "player1" in result.distributed_rewards
        assert "player2" in result.distributed_rewards
    
    def test_contribution_tracking_during_battle(self):
        """戦闘中の貢献度追跡テスト"""
        self.battle.add_participant(self.player1)
        
        # 攻撃アクションをシミュレート
        with patch.object(self.battle, '_create_battle_event'):
            action = self.battle.execute_player_action(
                "player1", 
                self.monster1.monster_id, 
                TurnActionType.ATTACK
            )
        
        # 貢献度が更新されていることを確認
        contribution = self.battle.player_contributions["player1"]
        assert contribution.successful_attacks > 0
    
    def test_minimum_contribution_score(self):
        """最低貢献度スコアのテスト"""
        contribution = PlayerContribution(player_id="test_player")
        score = contribution.calculate_contribution_score()
        
        # 最低スコアが保証されていることを確認
        assert score >= 1.0
    
    def test_equal_contribution_distribution(self):
        """同じ貢献度での分配テスト"""
        self.battle.add_participant(self.player1)
        self.battle.add_participant(self.player2)
        
        # 同じ貢献度を設定
        self.battle.player_contributions["player1"].total_damage_dealt = 100
        self.battle.player_contributions["player2"].total_damage_dealt = 100
        
        # モンスターを倒す
        self.monster1.take_damage(1000)
        
        total_rewards = self.battle._calculate_total_rewards([self.monster1])
        distributed_rewards = self.battle._calculate_contribution_based_rewards(total_rewards)
        
        # 同じ貢献度なら同じ報酬
        player1_reward = distributed_rewards["player1"]
        player2_reward = distributed_rewards["player2"]
        
        assert abs(player1_reward.money - player2_reward.money) <= 1  # 丸め誤差を考慮
        assert abs(player1_reward.experience - player2_reward.experience) <= 1
        assert player1_reward.contribution_percentage == player2_reward.contribution_percentage 