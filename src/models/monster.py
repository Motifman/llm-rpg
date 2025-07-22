from typing import List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from .item import Item
from .agent import Agent


class MonsterType(Enum):
    """モンスターのタイプ（将来の属性相性システム用）"""
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"  # 攻撃的（強制戦闘）
    HIDDEN = "hidden"         # 隠れている（探索が必要）
    PASSIVE = "passive"       # 受動的（こちらから戦闘開始が必要）


@dataclass
class MonsterDropReward:
    """モンスター撃破時の報酬"""
    items: List[Item] = field(default_factory=list)
    money: int = 0
    experience: int = 0
    information: List[str] = field(default_factory=list)


class Monster:
    """モンスタークラス"""
    
    def __init__(
        self,
        monster_id: str,
        name: str,
        description: str,
        monster_type: MonsterType,
        # バトルステータス
        max_hp: int = 50,
        attack: int = 8,
        defense: int = 3,
        speed: int = 5,
        # 新機能：属性・種族・状態異常
        race: Optional = None,  # Raceクラス
        element: Optional = None,  # Elementクラス
        # 移動範囲
        allowed_spots: Optional[Set[str]] = None,
        # 報酬
        drop_reward: Optional[MonsterDropReward] = None
    ):
        self.monster_id = monster_id
        self.name = name
        self.description = description
        self.monster_type = monster_type
        
        # バトルステータス
        self.max_hp = max_hp
        self.current_hp = max_hp
        self.attack = attack
        self.defense = defense
        self.speed = speed
        
        # 属性・種族システム
        from .weapon import Race, Element
        self.race = race if race else Race.MONSTER
        self.element = element if element else Element.PHYSICAL
        
        # 状態管理
        self.is_alive = True
        self.current_spot_id: Optional[str] = None
        
        # 状態異常システム
        self.status_conditions: List = []  # StatusConditionのリスト
        
        # 移動関連
        self.allowed_spots = allowed_spots or set()
        
        # 報酬
        self.drop_reward = drop_reward or MonsterDropReward()
        
        # バトル時の行動パターン（固定パターンで実装）
        self.battle_actions = ["attack", "defend"]  # 将来拡張予定
        
    def get_status_summary(self) -> str:
        """ステータスの要約を取得"""
        status = (f"HP: {self.current_hp}/{self.max_hp}, "
                 f"攻撃: {self.attack}, 防御: {self.defense}, "
                 f"素早さ: {self.speed}, "
                 f"種族: {self.race.value}, 属性: {self.element.value}")
        
        if self.status_conditions:
            status += f", 状態異常: {', '.join(str(c) for c in self.status_conditions)}"
        
        return status
    
    def take_damage(self, damage: int):
        """ダメージを受ける"""
        self.current_hp = max(0, self.current_hp - damage)
        if self.current_hp <= 0:
            self.is_alive = False
    
    def heal(self, amount: int):
        """回復する"""
        self.current_hp = min(self.max_hp, self.current_hp + amount)

    # === 状態異常システム ===
    
    def add_status_condition(self, condition):
        """状態異常を追加"""
        self.status_conditions.append(condition)
    
    def remove_status_condition(self, effect):
        """特定の状態異常を削除"""
        from .weapon import StatusEffect
        self.status_conditions = [c for c in self.status_conditions if c.effect != effect]
    
    def has_status_condition(self, effect) -> bool:
        """特定の状態異常があるかチェック"""
        from .weapon import StatusEffect
        return any(c.effect == effect for c in self.status_conditions)
    
    def process_status_effects(self):
        """状態異常の効果を処理（ターン終了時に呼ばれる）"""
        from .weapon import StatusEffect
        
        # 状態異常の効果を適用
        for condition in self.status_conditions[:]:  # コピーを作成して安全にイテレート
            if condition.effect == StatusEffect.POISON:
                # 毒ダメージ
                poison_damage = max(1, condition.value)
                self.current_hp = max(0, self.current_hp - poison_damage)
                if self.current_hp <= 0:
                    self.is_alive = False
            
            # ターン数を減らす
            condition.duration -= 1
            
            # 持続時間が終了した状態異常を削除
            if condition.duration <= 0:
                self.status_conditions.remove(condition)
    
    def can_act(self) -> bool:
        """行動可能かチェック（状態異常考慮）"""
        from .weapon import StatusEffect
        
        # 麻痺、睡眠の場合は行動不可
        if (self.has_status_condition(StatusEffect.PARALYSIS) or 
            self.has_status_condition(StatusEffect.SLEEP)):
            return False
        
        return self.is_alive
    
    def is_confused(self) -> bool:
        """混乱状態かチェック"""
        from .weapon import StatusEffect
        return self.has_status_condition(StatusEffect.CONFUSION)
    
    def is_silenced(self) -> bool:
        """沈黙状態かチェック（魔法攻撃不可）"""
        from .weapon import StatusEffect
        return self.has_status_condition(StatusEffect.SILENCE)

    # === 既存メソッド ===
    
    def can_move_to_spot(self, spot_id: str) -> bool:
        """指定されたスポットに移動可能かチェック"""
        if not self.allowed_spots:
            return True  # 制限なし
        return spot_id in self.allowed_spots
    
    def set_current_spot(self, spot_id: str):
        """現在のスポットを設定"""
        if self.can_move_to_spot(spot_id):
            self.current_spot_id = spot_id
        else:
            raise ValueError(f"モンスター {self.name} はスポット {spot_id} に移動できません")
    
    def get_current_spot_id(self) -> Optional[str]:
        """現在のスポットIDを取得"""
        return self.current_spot_id
    
    def is_battle_forced(self) -> bool:
        """強制戦闘が発生するかどうか"""
        return self.monster_type == MonsterType.AGGRESSIVE
    
    def requires_exploration_to_find(self) -> bool:
        """発見に探索が必要かどうか"""
        return self.monster_type == MonsterType.HIDDEN
    
    def is_passive(self) -> bool:
        """受動的（こちらから戦闘開始が必要）かどうか"""
        return self.monster_type == MonsterType.PASSIVE
    
    def get_battle_action(self) -> str:
        """バトル時の行動を決定（固定パターン）"""
        # 行動不可の場合
        if not self.can_act():
            return "unable_to_act"
        
        # 混乱の場合はランダム行動
        if self.is_confused():
            import random
            return random.choice(["attack", "defend", "confusion"])
        
        # 簡単な実装：HPが半分以下なら防御、それ以外は攻撃
        if self.current_hp <= self.max_hp // 2:
            return "defend"
        return "attack"
    
    def calculate_damage_to(self, target: Agent) -> int:
        """対象への攻撃ダメージを計算"""
        base_damage = max(1, self.attack - target.get_defense())
        return base_damage
    
    def calculate_damage_from(self, attacker: Agent) -> int:
        """攻撃者からのダメージを計算"""
        base_damage = max(1, attacker.get_attack() - self.defense)
        return base_damage
    
    def __str__(self):
        return f"Monster(id={self.monster_id}, name={self.name}, type={self.monster_type.value}, race={self.race.value}, element={self.element.value}, hp={self.current_hp}/{self.max_hp})"
    
    def __repr__(self):
        return self.__str__() 