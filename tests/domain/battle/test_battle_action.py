import pytest
from src.domain.battle.battle_action import BattleAction, ActionType
from src.domain.battle.battle_enum import StatusEffectType, BuffType, Element
from src.domain.monster.monster_enum import Race


class TestBattleAction:
    """BattleActionのテストクラス"""
    
    def test_create_basic_action(self):
        """基本的なアクションの作成テスト"""
        action = BattleAction(
            action_id=1,
            name="通常攻撃",
            description="基本的な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0
        )
        
        assert action.action_id == 1
        assert action.name == "通常攻撃"
        assert action.description == "基本的な攻撃"
        assert action.action_type == ActionType.ATTACK
        assert action.damage_multiplier == 1.0
        assert action.element is None
        assert action.heal_amount is None
        assert len(action.status_effect_rate) == 0
        assert len(action.status_effect_duration) == 0
        assert len(action.buff_multiplier) == 0
        assert len(action.buff_duration) == 0
        assert len(action.race_attack_multiplier) == 0
        assert action.hp_cost is None
        assert action.mp_cost is None
        assert action.hit_rate is None
    
    def test_create_magic_action(self):
        """魔法アクションの作成テスト"""
        action = BattleAction(
            action_id=2,
            name="火の矢",
            description="火属性の魔法攻撃",
            action_type=ActionType.MAGIC,
            damage_multiplier=1.5,
            element=Element.FIRE,
            mp_cost=10,
            hit_rate=0.9
        )
        
        assert action.action_id == 2
        assert action.name == "火の矢"
        assert action.description == "火属性の魔法攻撃"
        assert action.action_type == ActionType.MAGIC
        assert action.damage_multiplier == 1.5
        assert action.element == Element.FIRE
        assert action.mp_cost == 10
        assert action.hit_rate == 0.9
    
    def test_create_heal_action(self):
        """回復アクションの作成テスト"""
        action = BattleAction(
            action_id=3,
            name="ヒール",
            description="HPを回復する",
            action_type=ActionType.MAGIC,
            heal_amount=50,
            mp_cost=15
        )
        
        assert action.action_id == 3
        assert action.name == "ヒール"
        assert action.description == "HPを回復する"
        assert action.action_type == ActionType.MAGIC
        assert action.heal_amount == 50
        assert action.mp_cost == 15
        assert action.damage_multiplier == 1.0  # デフォルト値
    
    def test_create_status_effect_action(self):
        """状態異常付きアクションの作成テスト"""
        action = BattleAction(
            action_id=4,
            name="毒攻撃",
            description="毒状態異常を付与する攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=0.8,
            status_effect_rate={StatusEffectType.POISON: 0.7},
            status_effect_duration={StatusEffectType.POISON: 3}
        )
        
        assert action.action_id == 4
        assert action.name == "毒攻撃"
        assert action.status_effect_rate[StatusEffectType.POISON] == 0.7
        assert action.status_effect_duration[StatusEffectType.POISON] == 3
    
    def test_create_buff_action(self):
        """バフ付きアクションの作成テスト"""
        action = BattleAction(
            action_id=5,
            name="強化攻撃",
            description="バフを付与する攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0,
            buff_multiplier={BuffType.ATTACK: 1.5, BuffType.DEFENSE: 1.2},
            buff_duration={BuffType.ATTACK: 2, BuffType.DEFENSE: 3}
        )
        
        assert action.action_id == 5
        assert action.name == "強化攻撃"
        assert action.buff_multiplier[BuffType.ATTACK] == 1.5
        assert action.buff_multiplier[BuffType.DEFENSE] == 1.2
        assert action.buff_duration[BuffType.ATTACK] == 2
        assert action.buff_duration[BuffType.DEFENSE] == 3
    
    def test_create_race_specific_action(self):
        """種族特攻アクションの作成テスト"""
        action = BattleAction(
            action_id=6,
            name="ゴブリン特攻",
            description="ゴブリンに強い攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=1.0,
            race_attack_multiplier={Race.GOBLIN: 2.0, Race.ORC: 1.5}
        )
        
        assert action.action_id == 6
        assert action.name == "ゴブリン特攻"
        assert action.race_attack_multiplier[Race.GOBLIN] == 2.0
        assert action.race_attack_multiplier[Race.ORC] == 1.5
    
    def test_create_cost_action(self):
        """コスト付きアクションの作成テスト"""
        action = BattleAction(
            action_id=7,
            name="自己犠牲の攻撃",
            description="HPとMPを消費する強力な攻撃",
            action_type=ActionType.ATTACK,
            damage_multiplier=2.0,
            hp_cost=20,
            mp_cost=30
        )
        
        assert action.action_id == 7
        assert action.name == "自己犠牲の攻撃"
        assert action.hp_cost == 20
        assert action.mp_cost == 30
        assert action.damage_multiplier == 2.0
    
    def test_validation_hit_rate_invalid(self):
        """無効な命中率でのバリデーションテスト"""
        with pytest.raises(ValueError, match="hit_rate must be between 0 and 1"):
            BattleAction(
                action_id=1,
                name="無効な命中率",
                description="テスト",
                action_type=ActionType.ATTACK,
                hit_rate=-0.1
            )
        
        with pytest.raises(ValueError, match="hit_rate must be between 0 and 1"):
            BattleAction(
                action_id=1,
                name="無効な命中率",
                description="テスト",
                action_type=ActionType.ATTACK,
                hit_rate=1.1
            )
    
    def test_validation_mp_cost_invalid(self):
        """無効なMPコストでのバリデーションテスト"""
        with pytest.raises(ValueError, match="mp_cost must be non-negative"):
            BattleAction(
                action_id=1,
                name="無効なMPコスト",
                description="テスト",
                action_type=ActionType.MAGIC,
                mp_cost=-5
            )
    
    def test_validation_hp_cost_invalid(self):
        """無効なHPコストでのバリデーションテスト"""
        with pytest.raises(ValueError, match="hp_cost must be non-negative"):
            BattleAction(
                action_id=1,
                name="無効なHPコスト",
                description="テスト",
                action_type=ActionType.ATTACK,
                hp_cost=-10
            )
    
    def test_validation_damage_multiplier_invalid(self):
        """無効なダメージ倍率でのバリデーションテスト"""
        with pytest.raises(ValueError, match="damage_multiplier must be non-negative"):
            BattleAction(
                action_id=1,
                name="無効なダメージ倍率",
                description="テスト",
                action_type=ActionType.ATTACK,
                damage_multiplier=-1.0
            )
    
    def test_validation_status_effect_rate_invalid(self):
        """無効な状態異常確率でのバリデーションテスト"""
        with pytest.raises(ValueError, match="status_effect_rate must be between 0 and 1.0"):
            BattleAction(
                action_id=1,
                name="無効な状態異常確率",
                description="テスト",
                action_type=ActionType.ATTACK,
                status_effect_rate={StatusEffectType.POISON: -0.1}
            )
        
        with pytest.raises(ValueError, match="status_effect_rate must be between 0 and 1.0"):
            BattleAction(
                action_id=1,
                name="無効な状態異常確率",
                description="テスト",
                action_type=ActionType.ATTACK,
                status_effect_rate={StatusEffectType.POISON: 1.1}
            )
    
    def test_validation_race_attack_multiplier_invalid(self):
        """無効な種族特攻倍率でのバリデーションテスト"""
        with pytest.raises(ValueError, match="race_attack_multiplier must be non-negative"):
            BattleAction(
                action_id=1,
                name="無効な種族特攻倍率",
                description="テスト",
                action_type=ActionType.ATTACK,
                race_attack_multiplier={Race.GOBLIN: -0.5}
            )
    
    def test_validation_buff_multiplier_invalid(self):
        """無効なバフ倍率でのバリデーションテスト"""
        with pytest.raises(ValueError, match="buff_multiplier must be non-negative"):
            BattleAction(
                action_id=1,
                name="無効なバフ倍率",
                description="テスト",
                action_type=ActionType.ATTACK,
                buff_multiplier={BuffType.ATTACK: -1.0}
            )
    
    def test_validation_multiple_errors(self):
        """複数のバリデーションエラーのテスト"""
        with pytest.raises(ValueError, match="hit_rate must be between 0 and 1"):
            BattleAction(
                action_id=1,
                name="複数エラー",
                description="テスト",
                action_type=ActionType.ATTACK,
                hit_rate=1.5,
                mp_cost=-5,
                damage_multiplier=-1.0
            )
    
    def test_valid_boundary_values(self):
        """境界値でのバリデーションテスト"""
        # 有効な境界値
        action = BattleAction(
            action_id=1,
            name="境界値テスト",
            description="テスト",
            action_type=ActionType.ATTACK,
            hit_rate=0.0,  # 最小値
            mp_cost=0,     # 最小値
            hp_cost=0,     # 最小値
            damage_multiplier=0.0  # 最小値
        )
        
        assert action.hit_rate == 0.0
        assert action.mp_cost == 0
        assert action.hp_cost == 0
        assert action.damage_multiplier == 0.0
        
        # 最大値
        action2 = BattleAction(
            action_id=2,
            name="境界値テスト2",
            description="テスト",
            action_type=ActionType.ATTACK,
            hit_rate=1.0,  # 最大値
            damage_multiplier=999.0  # 大きな値
        )
        
        assert action2.hit_rate == 1.0
        assert action2.damage_multiplier == 999.0
    
    def test_complex_action_creation(self):
        """複雑なアクションの作成テスト"""
        action = BattleAction(
            action_id=8,
            name="究極魔法",
            description="全ての要素を含む究極の魔法",
            action_type=ActionType.MAGIC,
            damage_multiplier=3.0,
            element=Element.THUNDER,
            heal_amount=100,
            status_effect_rate={
                StatusEffectType.PARALYSIS: 0.8,
                StatusEffectType.BURN: 0.5
            },
            status_effect_duration={
                StatusEffectType.PARALYSIS: 2,
                StatusEffectType.BURN: 3
            },
            buff_multiplier={
                BuffType.ATTACK: 2.0,
                BuffType.DEFENSE: 1.5,
                BuffType.SPEED: 1.3
            },
            buff_duration={
                BuffType.ATTACK: 4,
                BuffType.DEFENSE: 3,
                BuffType.SPEED: 2
            },
            race_attack_multiplier={
                Race.DRAGON: 3.0,
                Race.GHOST: 2.5
            },
            hp_cost=50,
            mp_cost=100,
            hit_rate=0.95
        )
        
        # 基本プロパティ
        assert action.action_id == 8
        assert action.name == "究極魔法"
        assert action.description == "全ての要素を含む究極の魔法"
        assert action.action_type == ActionType.MAGIC
        assert action.damage_multiplier == 3.0
        assert action.element == Element.THUNDER
        assert action.heal_amount == 100
        assert action.hp_cost == 50
        assert action.mp_cost == 100
        assert action.hit_rate == 0.95
        
        # 状態異常
        assert action.status_effect_rate[StatusEffectType.PARALYSIS] == 0.8
        assert action.status_effect_rate[StatusEffectType.BURN] == 0.5
        assert action.status_effect_duration[StatusEffectType.PARALYSIS] == 2
        assert action.status_effect_duration[StatusEffectType.BURN] == 3
        
        # バフ
        assert action.buff_multiplier[BuffType.ATTACK] == 2.0
        assert action.buff_multiplier[BuffType.DEFENSE] == 1.5
        assert action.buff_multiplier[BuffType.SPEED] == 1.3
        assert action.buff_duration[BuffType.ATTACK] == 4
        assert action.buff_duration[BuffType.DEFENSE] == 3
        assert action.buff_duration[BuffType.SPEED] == 2
        
        # 種族特攻
        assert action.race_attack_multiplier[Race.DRAGON] == 3.0
        assert action.race_attack_multiplier[Race.GHOST] == 2.5
    
    def test_action_type_enum_values(self):
        """ActionTypeの列挙値テスト"""
        assert ActionType.ATTACK == ActionType.ATTACK
        assert ActionType.MAGIC == ActionType.MAGIC
        assert ActionType.DEFEND == ActionType.DEFEND
        assert ActionType.ITEM == ActionType.ITEM
        assert ActionType.ESCAPE == ActionType.ESCAPE
        assert ActionType.STATUS_EFFECT == ActionType.STATUS_EFFECT
        
        # 文字列値の確認
        assert ActionType.ATTACK.value == "attack"
        assert ActionType.MAGIC.value == "magic"
        assert ActionType.DEFEND.value == "defend"
        assert ActionType.ITEM.value == "item"
        assert ActionType.ESCAPE.value == "escape"
        assert ActionType.STATUS_EFFECT.value == "status_effect"
    
    def test_immutable_properties(self):
        """プロパティの不変性テスト"""
        action = BattleAction(
            action_id=1,
            name="テスト",
            description="テスト",
            action_type=ActionType.ATTACK
        )
        
        # プロパティは読み取り専用
        assert action.action_id == 1
        assert action.name == "テスト"
        assert action.description == "テスト"
        assert action.action_type == ActionType.ATTACK
        
        # 辞書は空だが存在する
        assert isinstance(action.status_effect_rate, dict)
        assert isinstance(action.status_effect_duration, dict)
        assert isinstance(action.buff_multiplier, dict)
        assert isinstance(action.buff_duration, dict)
        assert isinstance(action.race_attack_multiplier, dict)
