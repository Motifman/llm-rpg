import pytest
from unittest.mock import Mock, patch
from src.domain.battle.battle_service import BattleService
from src.domain.battle.battle_participant import BattleParticipant
from src.domain.battle.battle_action import BattleAction, ActionType
from src.domain.battle.battle_result import BattleActionResult, TurnStartResult, TurnEndResult
from src.domain.battle.battle_enum import StatusEffectType, BuffType, Element
from src.domain.monster.monster_enum import Race
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus


class MockCombatEntity:
    """テスト用のモック戦闘エンティティ"""
    def __init__(
        self,
        name: str,
        attack: int = 10,
        defense: int = 5,
        speed: int = 8,
        hp: int = 100,
        mp: int = 50,
        max_hp: int = 100,
        max_mp: int = 50,
        critical_rate: float = 0.1,
        evasion_rate: float = 0.05,
        element: Element = Element.NEUTRAL,
        race: Race = Race.HUMAN,
        is_defending: bool = False
    ):
        self.name = name
        self._attack = attack
        self._defense = defense
        self._speed = speed
        self._hp = hp
        self._mp = mp
        self._max_hp = max_hp
        self._max_mp = max_mp
        self._critical_rate = critical_rate
        self._evasion_rate = evasion_rate
        self._element = element
        self._race = race
        self._is_defending = is_defending
    
    @property
    def attack(self) -> int:
        return self._attack
    
    @property
    def defense(self) -> int:
        return self._defense
    
    @property
    def speed(self) -> int:
        return self._speed
    
    @property
    def hp(self) -> int:
        return self._hp
    
    @property
    def mp(self) -> int:
        return self._mp
    
    @property
    def max_hp(self) -> int:
        return self._max_hp
    
    @property
    def max_mp(self) -> int:
        return self._max_mp
    
    @property
    def critical_rate(self) -> float:
        return self._critical_rate
    
    @property
    def evasion_rate(self) -> float:
        return self._evasion_rate
    
    @property
    def element(self) -> Element:
        return self._element
    
    @property
    def race(self) -> Race:
        return self._race
    
    def take_damage(self, damage: int):
        self._hp = max(0, self._hp - damage)
    
    def heal(self, amount: int):
        self._hp = min(self._max_hp, self._hp + amount)
    
    def consume_mp(self, amount: int):
        self._mp = max(0, self._mp - amount)
    
    def can_consume_mp(self, amount: int) -> bool:
        return self._mp >= amount
    
    def is_alive(self) -> bool:
        return self._hp > 0
    
    def is_defending(self) -> bool:
        return self._is_defending
    
    def defend(self):
        self._is_defending = True
    
    def un_defend(self):
        self._is_defending = False


class TestBattleService:
    """BattleServiceのテストクラス"""
    
    def setup_method(self):
        """テスト用のBattleServiceを作成"""
        self.battle_service = BattleService()
        
        # テスト用のエンティティを作成
        self.attacker_entity = MockCombatEntity(
            name="攻撃者",
            attack=20,
            defense=5,
            hp=100,
            mp=50,
            element=Element.FIRE,
            race=Race.HUMAN
        )
        
        self.defender_entity = MockCombatEntity(
            name="防御者",
            attack=15,
            defense=10,
            hp=80,
            mp=30,
            element=Element.GRASS,
            race=Race.GOBLIN
        )
        
        # テスト用のBattleParticipantを作成
        self.attacker = BattleParticipant.create(self.attacker_entity, 1)
        self.defender = BattleParticipant.create(self.defender_entity, 2)
    
    def test_check_rate(self):
        """確率チェックのテスト"""
        # 100%の確率
        assert self.battle_service._check_rate(1.0) is True
        
        # 0%の確率
        assert self.battle_service._check_rate(0.0) is False
        
        # 50%の確率（複数回実行して統計的に確認）
        true_count = 0
        for _ in range(1000):
            if self.battle_service._check_rate(0.5):
                true_count += 1
        
        # 50% ± 5%の範囲内にあることを確認
        assert 450 <= true_count <= 550
    
    def test_check_compatible_multiplier(self):
        """相性チェックのテスト"""
        # 火属性の攻撃が草属性に強い
        fire_action = BattleAction(
            action_id=1,
            name="火の矢",
            description="火属性の攻撃",
            action_type=ActionType.MAGIC,
            element=Element.FIRE
        )
        
        multiplier = self.battle_service._check_compatible_multiplier(fire_action, self.defender)
        assert multiplier == 1.5  # 火→草は強い
        
        # 水属性の攻撃が火属性に強い
        water_action = BattleAction(
            action_id=2,
            name="水の矢",
            description="水属性の攻撃",
            action_type=ActionType.MAGIC,
            element=Element.WATER
        )
        
        fire_defender = MockCombatEntity(
            name="火の敵",
            element=Element.FIRE
        )
        fire_defender_participant = BattleParticipant.create(fire_defender, 3)
        
        multiplier = self.battle_service._check_compatible_multiplier(water_action, fire_defender_participant)
        assert multiplier == 1.5  # 水→火は強い
        
        # 相性なしの場合
        neutral_action = BattleAction(
            action_id=3,
            name="通常攻撃",
            description="属性なしの攻撃",
            action_type=ActionType.ATTACK,
            element=Element.NEUTRAL
        )
        
        multiplier = self.battle_service._check_compatible_multiplier(neutral_action, self.defender)
        assert multiplier == 1.0  # 相性なし
    
    def test_calculate_damage_basic(self):
        """基本的なダメージ計算のテスト"""
        action = BattleAction(
            action_id=1,
            name="通常攻撃",
            description="基本的な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        damage = self.battle_service._calculate_damage(self.attacker, self.defender, action, False)
        
        # 基本ダメージ: 攻撃力(20) * 倍率(1.0) - 防御力(10) = 10
        expected_damage = 20 - 10
        assert damage == expected_damage
    
    def test_calculate_damage_with_multiplier(self):
        """ダメージ倍率付きの計算テスト"""
        action = BattleAction(
            action_id=1,
            name="強力な攻撃",
            description="ダメージ倍率が高い攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=2.0
        )
        
        damage = self.battle_service._calculate_damage(self.attacker, self.defender, action, False)
        
        # 基本ダメージ: 攻撃力(20) * 倍率(2.0) - 防御力(10) = 30
        expected_damage = 20 * 2.0 - 10
        assert damage == expected_damage
    
    def test_calculate_damage_with_critical(self):
        """クリティカルダメージの計算テスト"""
        action = BattleAction(
            action_id=1,
            name="通常攻撃",
            description="基本的な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        damage = self.battle_service._calculate_damage(self.attacker, self.defender, action, True)
        
        # 基本ダメージ: (攻撃力(20) * 倍率(1.0) - 防御力(10)) * クリティカル倍率(1.5) = 15
        expected_damage = int((20 - 10) * 1.5)
        assert damage == expected_damage
    
    def test_calculate_damage_with_defense(self):
        """防御状態でのダメージ計算テスト"""
        # 防御者を防御状態にする
        self.defender_entity.defend()
        
        action = BattleAction(
            action_id=1,
            name="通常攻撃",
            description="基本的な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        damage = self.battle_service._calculate_damage(self.attacker, self.defender, action, False)
        
        # 基本ダメージ: 攻撃力(20) * 倍率(1.0) - (防御力(10) * 防御倍率(0.5)) = 15
        expected_damage = 20 - (10 * 0.5)
        assert damage == expected_damage
    
    def test_calculate_damage_with_race_multiplier(self):
        """種族特攻のダメージ計算テスト"""
        action = BattleAction(
            action_id=1,
            name="ゴブリン特攻",
            description="ゴブリンに強い攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0,
            race_attack_multiplier={Race.GOBLIN: 2.0}
        )
        
        damage = self.battle_service._calculate_damage(self.attacker, self.defender, action, False)
        
        # 基本ダメージ: (攻撃力(20) * 倍率(1.0) * 種族倍率(2.0)) - 防御力(10) = 30
        expected_damage = (20 * 2.0) - 10
        assert damage == expected_damage
    
    def test_calculate_damage_minimum_zero(self):
        """ダメージが0未満にならないことを確認"""
        # 防御力が攻撃力より高い場合
        high_defense_entity = MockCombatEntity(
            name="高防御",
            attack=5,
            defense=20
        )
        high_defense_participant = BattleParticipant.create(high_defense_entity, 4)
        
        action = BattleAction(
            action_id=1,
            name="弱い攻撃",
            description="弱い攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        damage = self.battle_service._calculate_damage(self.attacker, high_defense_participant, action, False)
        
        # ダメージは0以上である必要がある
        assert damage >= 0
    
    def test_process_turn_start_normal(self):
        """通常のターン開始処理のテスト"""
        result = self.battle_service.process_turn_start(self.attacker)
        
        assert result.can_act is True
        assert len(result.messages) == 0
        assert result.self_damage == 0
        assert len(result.recovered_status_effects) == 0
    
    def test_process_turn_start_sleep(self):
        """睡眠状態でのターン開始処理のテスト"""
        # 睡眠状態を追加
        self.attacker.add_status_effect(StatusEffectType.SLEEP, 3)
        
        with patch.object(self.battle_service, '_check_rate') as mock_check_rate:
            # 睡眠から覚めない場合
            mock_check_rate.return_value = False
            result = self.battle_service.process_turn_start(self.attacker)
            
            assert result.can_act is False
            assert len(result.messages) == 1
            assert "眠っている" in result.messages[0]
            
            # 睡眠から覚める場合
            mock_check_rate.return_value = True
            result = self.battle_service.process_turn_start(self.attacker)
            
            assert result.can_act is True
            assert len(result.messages) == 1
            assert "眠りから覚めた" in result.messages[0]
            assert StatusEffectType.SLEEP in result.recovered_status_effects
    
    def test_process_turn_start_paralysis(self):
        """麻痺状態でのターン開始処理のテスト"""
        # 麻痺状態を追加
        self.attacker.add_status_effect(StatusEffectType.PARALYSIS, 2)
        
        result = self.battle_service.process_turn_start(self.attacker)
        
        assert result.can_act is False
        assert len(result.messages) == 1
        assert "麻痺" in result.messages[0]
    
    def test_process_turn_start_confusion(self):
        """混乱状態でのターン開始処理のテスト"""
        # 混乱状態を追加
        self.attacker.add_status_effect(StatusEffectType.CONFUSION, 2)
        
        result = self.battle_service.process_turn_start(self.attacker)
        
        assert result.can_act is False
        assert result.self_damage > 0
        assert len(result.messages) == 1
        assert "混乱" in result.messages[0]
        assert "自分に" in result.messages[0]
    
    def test_process_turn_start_curse(self):
        """呪い状態でのターン開始処理のテスト"""
        # 呪い状態を追加
        self.attacker.add_status_effect(StatusEffectType.CURSE, 3)
        
        result = self.battle_service.process_turn_start(self.attacker)
        
        assert result.can_act is True
        assert len(result.messages) == 1
        assert "呪い" in result.messages[0]
        assert "残り3ターン" in result.messages[0]
    
    def test_process_turn_end_normal(self):
        """通常のターン終了処理のテスト"""
        result = self.battle_service.process_turn_end(self.attacker)
        
        assert result.is_attacker_defeated is False
        assert len(result.messages) == 0
        assert result.damage_from_status_effects == 0
        assert result.healing_from_status_effects == 0
    
    def test_process_turn_end_burn(self):
        """火傷状態でのターン終了処理のテスト"""
        # 火傷状態を追加
        self.attacker.add_status_effect(StatusEffectType.BURN, 2)
        
        result = self.battle_service.process_turn_end(self.attacker)
        
        assert result.damage_from_status_effects == 20  # BURN_DAMAGE_AMOUNT
        assert len(result.messages) == 1
        assert "やけど" in result.messages[0]
        assert "20のダメージ" in result.messages[0]
    
    def test_process_turn_end_poison(self):
        """毒状態でのターン終了処理のテスト"""
        # 毒状態を追加
        self.attacker.add_status_effect(StatusEffectType.POISON, 2)
        
        result = self.battle_service.process_turn_end(self.attacker)
        
        # 毒ダメージ: HP(100) * 0.1 = 10
        expected_damage = int(100 * 0.1)
        assert result.damage_from_status_effects == expected_damage
        assert len(result.messages) == 1
        assert "毒" in result.messages[0]
    
    def test_process_turn_end_blessing(self):
        """祝福状態でのターン終了処理のテスト"""
        # 祝福状態を追加
        self.attacker.add_status_effect(StatusEffectType.BLESSING, 2)
        
        result = self.battle_service.process_turn_end(self.attacker)
        
        assert result.healing_from_status_effects == 20  # BLESSING_HEAL_AMOUNT
        assert len(result.messages) == 1
        assert "神の加護" in result.messages[0]
        assert "20HP回復" in result.messages[0]
    
    def test_process_turn_end_curse_expired(self):
        """呪い期限切れでのターン終了処理のテスト"""
        # 呪い状態を追加（残り1ターン）
        self.attacker.add_status_effect(StatusEffectType.CURSE, 1)
        
        # ターン開始で残りターンを0にする
        self.battle_service.process_turn_start(self.attacker)
        
        result = self.battle_service.process_turn_end(self.attacker)
        
        # 呪いが発動してHP分のダメージ
        assert result.damage_from_status_effects == 100  # 現在のHP
        assert len(result.messages) == 1
        assert "呪いが発動" in result.messages[0]
        assert StatusEffectType.CURSE in result.expired_status_effects
    
    def test_execute_attack_success(self):
        """攻撃実行の成功テスト"""
        action = BattleAction(
            action_id=1,
            name="通常攻撃",
            description="基本的な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        with patch.object(self.battle_service, '_check_rate') as mock_check_rate:
            # 回避率チェックは失敗（回避しない）
            mock_check_rate.side_effect = lambda rate: rate != self.defender_entity.evasion_rate
            
            result = self.battle_service.execute_attack(self.attacker, [self.defender], action)
            
            assert result.success is True
            assert len(result.messages) == 1
            assert "ダメージを与えた" in result.messages[0]
            assert len(result.target_ids) == 1
            assert result.target_ids[0] == 2
            assert len(result.damages) == 1
            assert result.damages[0] > 0
            assert len(result.is_target_defeated) == 1
            assert result.is_target_defeated[0] is False
    
    def test_execute_attack_multiple_targets(self):
        """複数ターゲットへの攻撃テスト"""
        # 2番目の防御者を作成
        defender2_entity = MockCombatEntity(
            name="防御者2",
            attack=12,
            defense=8,
            hp=60,
            mp=25
        )
        defender2 = BattleParticipant.create(defender2_entity, 3)
        
        action = BattleAction(
            action_id=1,
            name="範囲攻撃",
            description="複数にダメージを与える攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        result = self.battle_service.execute_attack(self.attacker, [self.defender, defender2], action)
        
        assert result.success is True
        assert len(result.target_ids) == 2
        assert result.target_ids == [2, 3]
        assert len(result.damages) == 2
        assert all(damage > 0 for damage in result.damages)
        assert len(result.is_target_defeated) == 2
    
    def test_execute_attack_insufficient_mp(self):
        """MP不足での攻撃失敗テスト"""
        action = BattleAction(
            action_id=1,
            name="魔法攻撃",
            description="MPを消費する攻撃",
            action_type=ActionType.MAGIC,
            damage_multiplier=1.0,
            mp_cost=100  # 現在のMP(50)より多い
        )
        
        result = self.battle_service.execute_attack(self.attacker, [self.defender], action)
        
        assert result.success is False
        assert result.failure_reason == "insufficient_mp"
        assert len(result.messages) == 1
        assert "MPが足りず" in result.messages[0]
    
    def test_execute_attack_silenced(self):
        """沈黙状態での魔法攻撃失敗テスト"""
        # 沈黙状態を追加
        self.attacker.add_status_effect(StatusEffectType.SILENCE, 2)
        
        action = BattleAction(
            action_id=1,
            name="魔法攻撃",
            description="MPを消費する攻撃",
            action_type=ActionType.MAGIC,
            damage_multiplier=1.0,
            mp_cost=10
        )
        
        result = self.battle_service.execute_attack(self.attacker, [self.defender], action)
        
        assert result.success is False
        assert result.failure_reason == "silenced"
        assert len(result.messages) == 1
        assert "沈黙" in result.messages[0]
    
    def test_execute_attack_miss(self):
        """攻撃ミスのテスト"""
        action = BattleAction(
            action_id=1,
            name="命中率の低い攻撃",
            description="命中率が低い攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0,
            hit_rate=0.0  # 必ずミス
        )
        
        result = self.battle_service.execute_attack(self.attacker, [self.defender], action)
        
        assert result.success is False
        assert result.failure_reason == "missed"
        assert len(result.messages) == 1
        assert "外れた" in result.messages[0]
    
    def test_execute_attack_evaded(self):
        """攻撃回避のテスト"""
        # 回避率100%の防御者を作成
        evasive_entity = MockCombatEntity(
            name="回避者",
            attack=10,
            defense=5,
            hp=50,
            evasion_rate=1.0  # 必ず回避
        )
        evasive_defender = BattleParticipant.create(evasive_entity, 4)
        
        action = BattleAction(
            action_id=1,
            name="通常攻撃",
            description="基本的な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        result = self.battle_service.execute_attack(self.attacker, [evasive_defender], action)
        
        assert result.success is False
        assert result.failure_reason == "evaded"
        assert len(result.messages) == 1
        assert "回避" in result.messages[0]
    
    def test_execute_attack_multiple_targets_partial_evasion(self):
        """複数対象攻撃で一部が回避するテスト"""
        # 回避率100%の防御者を作成
        evasive_entity = MockCombatEntity(
            name="回避者",
            attack=10,
            defense=5,
            hp=50,
            evasion_rate=1.0  # 必ず回避
        )
        evasive_defender = BattleParticipant.create(evasive_entity, 4)
        
        # 回避率0%の防御者を作成
        non_evasive_entity = MockCombatEntity(
            name="防御者",
            attack=15,
            defense=10,
            hp=80,
            evasion_rate=0.0  # 回避しない
        )
        non_evasive_defender = BattleParticipant.create(non_evasive_entity, 5)
        
        action = BattleAction(
            action_id=1,
            name="範囲攻撃",
            description="複数にダメージを与える攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        result = self.battle_service.execute_attack(self.attacker, [non_evasive_defender, evasive_defender], action)
        
        assert result.success is True
        assert len(result.target_ids) == 2
        assert result.target_ids == [5, 4]
        assert len(result.damages) == 2
        assert result.damages[0] > 0  # 回避しないdefenderはダメージを受ける
        assert result.damages[1] == 0  # 回避したdefenderはダメージ0
        assert len(result.messages) >= 2
        assert any("回避" in msg for msg in result.messages)
        assert any("ダメージを与えた" in msg for msg in result.messages)
    
    def test_execute_attack_multiple_targets_all_evaded(self):
        """複数対象攻撃で全員が回避するテスト"""
        # 回避率100%の防御者を2人作成
        evasive_entity1 = MockCombatEntity(
            name="回避者1",
            attack=10,
            defense=5,
            hp=50,
            evasion_rate=1.0  # 必ず回避
        )
        evasive_entity2 = MockCombatEntity(
            name="回避者2",
            attack=10,
            defense=5,
            hp=50,
            evasion_rate=1.0  # 必ず回避
        )
        evasive_defender1 = BattleParticipant.create(evasive_entity1, 4)
        evasive_defender2 = BattleParticipant.create(evasive_entity2, 5)
        
        action = BattleAction(
            action_id=1,
            name="範囲攻撃",
            description="複数にダメージを与える攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        result = self.battle_service.execute_attack(self.attacker, [evasive_defender1, evasive_defender2], action)
        
        assert result.success is False
        assert result.failure_reason == "evaded"
        assert len(result.messages) == 2
        assert all("回避" in msg for msg in result.messages)
    
    def test_execute_attack_with_status_effects(self):
        """状態異常付き攻撃のテスト"""
        action = BattleAction(
            action_id=1,
            name="毒攻撃",
            description="毒状態異常を付与する攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0,
            status_effect_rate={StatusEffectType.POISON: 1.0},  # 必ず毒状態
            status_effect_duration={StatusEffectType.POISON: 3}
        )
        
        with patch.object(self.battle_service, '_check_rate') as mock_check_rate:
            # 回避率チェックは失敗、状態異常付与は成功
            mock_check_rate.side_effect = lambda rate: rate != self.defender_entity.evasion_rate
            
            result = self.battle_service.execute_attack(self.attacker, [self.defender], action)
            
            assert result.success is True
            assert len(result.applied_status_effects) == 1
            assert result.applied_status_effects[0][0] == 2  # target_id
            assert result.applied_status_effects[0][1] == StatusEffectType.POISON
            assert result.applied_status_effects[0][2] == 3  # duration
    
    def test_execute_attack_with_buffs(self):
        """バフ付き攻撃のテスト"""
        action = BattleAction(
            action_id=1,
            name="強化攻撃",
            description="バフを付与する攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0,
            buff_multiplier={BuffType.ATTACK: 1.5},
            buff_duration={BuffType.ATTACK: 2}
        )
        
        result = self.battle_service.execute_attack(self.attacker, [self.defender], action)
        
        assert result.success is True
        assert len(result.applied_buffs) == 1
        assert result.applied_buffs[0][0] == 2  # target_id
        assert result.applied_buffs[0][1] == BuffType.ATTACK
        assert result.applied_buffs[0][2] == 1.5  # multiplier
        assert result.applied_buffs[0][3] == 2  # duration
    
    def test_execute_attack_target_defeated(self):
        """ターゲット撃破のテスト"""
        # HPが低い防御者を作成
        weak_entity = MockCombatEntity(
            name="弱い敵",
            attack=5,
            defense=2,
            hp=5,  # 低いHP
            evasion_rate=0.0  # 回避しない
        )
        weak_defender = BattleParticipant.create(weak_entity, 5)
        
        action = BattleAction(
            action_id=1,
            name="強力な攻撃",
            description="強力な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=2.0
        )
        
        result = self.battle_service.execute_attack(self.attacker, [weak_defender], action)
        
        assert result.success is True
        assert len(result.is_target_defeated) == 1
        assert result.is_target_defeated[0] is True
    
    def test_execute_defend(self):
        """防御実行のテスト"""
        action = BattleAction(
            action_id=1,
            name="防御",
            description="防御の構えをとる",
            action_type=ActionType.DEFEND
        )
        
        result = self.battle_service.execute_defend(self.defender, action)
        
        assert result.success is True
        assert len(result.messages) == 1
        assert "守りの構え" in result.messages[0]
        assert self.defender_entity.is_defending() is True
    
    def test_execute_heal_success(self):
        """回復実行の成功テスト"""
        # HPが低い防御者を作成
        injured_entity = MockCombatEntity(
            name="負傷者",
            attack=8,
            defense=4,
            hp=20,  # 低いHP
            max_hp=100
        )
        injured_defender = BattleParticipant.create(injured_entity, 6)
        
        action = BattleAction(
            action_id=1,
            name="ヒール",
            description="HPを回復する",
            action_type=ActionType.MAGIC,
            mp_cost=10,
            heal_amount=30
        )
        
        result = self.battle_service.execute_heal(self.attacker, injured_defender, action)
        
        assert result.success is True
        assert len(result.messages) == 2  # MP消費 + 回復
        assert "MPを消費" in result.messages[0]
        assert "HP回復" in result.messages[1]
        assert len(result.healing_amounts) == 1
        assert result.healing_amounts[0] == 30
        assert result.hp_consumed == 0
        assert result.mp_consumed == 10
    
    def test_execute_heal_insufficient_mp(self):
        """MP不足での回復失敗テスト"""
        action = BattleAction(
            action_id=1,
            name="ヒール",
            description="HPを回復する",
            action_type=ActionType.MAGIC,
            mp_cost=100,  # 現在のMP(50)より多い
            heal_amount=30
        )
        
        result = self.battle_service.execute_heal(self.attacker, self.defender, action)
        
        assert result.success is False
        assert result.failure_reason == "insufficient_mp"
        assert len(result.messages) == 1
        assert "MPが足りず" in result.messages[0]
    
    def test_execute_heal_with_hp_cost(self):
        """HPコスト付き回復のテスト"""
        action = BattleAction(
            action_id=1,
            name="自己犠牲の回復",
            description="HPを消費して回復する",
            action_type=ActionType.MAGIC,
            mp_cost=5,
            hp_cost=10,
            heal_amount=50
        )
        
        result = self.battle_service.execute_heal(self.attacker, self.defender, action)
        
        assert result.success is True
        assert len(result.messages) == 3  # MP消費 + HP消費 + 回復
        assert "MPを消費" in result.messages[0]
        assert "HPを消費" in result.messages[1]
        assert "HP回復" in result.messages[2]
        assert result.hp_consumed == 10
        assert result.mp_consumed == 5
    
    def test_buff_multiplier_calculation(self):
        """バフ倍率計算のテスト"""
        # 攻撃力バフを追加
        self.attacker.add_buff(BuffType.ATTACK, 3, 1.5)
        
        action = BattleAction(
            action_id=1,
            name="通常攻撃",
            description="基本的な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        damage = self.battle_service._calculate_damage(self.attacker, self.defender, action, False)
        
        # 基本ダメージ: (攻撃力(20) * バフ倍率(1.5)) - 防御力(10) = 20
        expected_damage = (20 * 1.5) - 10
        assert damage == expected_damage
    
    def test_defense_buff_multiplier_calculation(self):
        """防御バフ倍率計算のテスト"""
        # 防御力バフを追加
        self.defender.add_buff(BuffType.DEFENSE, 3, 1.5)
        
        action = BattleAction(
            action_id=1,
            name="通常攻撃",
            description="基本的な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        damage = self.battle_service._calculate_damage(self.attacker, self.defender, action, False)
        
        # 基本ダメージ: 攻撃力(20) - (防御力(10) * バフ倍率(1.5)) = 5
        expected_damage = 20 - (10 * 1.5)
        assert damage == expected_damage
    
    def test_status_effect_duration_management(self):
        """状態異常の持続時間管理のテスト"""
        # 状態異常を追加
        self.attacker.add_status_effect(StatusEffectType.POISON, 3)
        
        # 1ターン目: 開始処理
        self.battle_service.process_turn_start(self.attacker)
        # 残りターン数が減っていることを確認
        remaining_duration = self.attacker.get_status_effect_remaining_duration(StatusEffectType.POISON)
        assert remaining_duration == 2
        
        # 1ターン目: 終了処理
        self.battle_service.process_turn_end(self.attacker)
        # まだ残りターン数があるので削除されない
        assert self.attacker.has_status_effect(StatusEffectType.POISON)
        
        # 2ターン目: 開始処理
        self.battle_service.process_turn_start(self.attacker)
        remaining_duration = self.attacker.get_status_effect_remaining_duration(StatusEffectType.POISON)
        assert remaining_duration == 1
        
        # 2ターン目: 終了処理
        self.battle_service.process_turn_end(self.attacker)
        # まだ残りターン数があるので削除されない
        assert self.attacker.has_status_effect(StatusEffectType.POISON)
        
        # 3ターン目: 開始処理
        self.battle_service.process_turn_start(self.attacker)
        remaining_duration = self.attacker.get_status_effect_remaining_duration(StatusEffectType.POISON)
        assert remaining_duration == 0
        
        # 3ターン目: 終了処理
        self.battle_service.process_turn_end(self.attacker)
        # 残りターン数が0になった状態異常は削除される
        remaining_duration = self.attacker.get_status_effect_remaining_duration(StatusEffectType.POISON)
        assert remaining_duration == 0
        assert not self.attacker.has_status_effect(StatusEffectType.POISON)
    
    def test_buff_duration_management(self):
        """バフの持続時間管理のテスト"""
        # バフを追加
        self.attacker.add_buff(BuffType.ATTACK, 2, 1.5)
        
        # 1ターン目: 開始処理
        self.battle_service.process_turn_start(self.attacker)
        # 残りターン数が減っていることを確認
        remaining_duration = self.attacker.buffs_remaining_duration[BuffType.ATTACK]
        assert remaining_duration == 1
        
        # 1ターン目: 終了処理
        self.battle_service.process_turn_end(self.attacker)
        # まだ残りターン数があるので削除されない
        assert BuffType.ATTACK in self.attacker.buffs_remaining_duration
        
        # 2ターン目: 開始処理
        self.battle_service.process_turn_start(self.attacker)
        remaining_duration = self.attacker.buffs_remaining_duration[BuffType.ATTACK]
        assert remaining_duration == 0
        
        # 2ターン目: 終了処理
        self.battle_service.process_turn_end(self.attacker)
        # 残りターン数が0になったバフは削除される
        assert BuffType.ATTACK not in self.attacker.buffs_remaining_duration
        assert BuffType.ATTACK not in self.attacker.buffs_multiplier
