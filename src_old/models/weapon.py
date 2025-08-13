from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from .agent import Agent

from .item import Item


# === 属性システム ===

class Element(Enum):
    """属性タイプ"""
    FIRE = "fire"      # 炎
    ICE = "ice"        # 氷
    THUNDER = "thunder" # 雷
    HOLY = "holy"      # 聖
    DARK = "dark"      # 闇
    PHYSICAL = "physical"  # 物理（デフォルト）


class Race(Enum):
    """種族タイプ（種族特攻用）"""
    HUMAN = "human"
    MONSTER = "monster"
    UNDEAD = "undead"
    DRAGON = "dragon"
    BEAST = "beast"
    DEMON = "demon"


# === 状態異常システム ===

class StatusEffect(Enum):
    """状態異常タイプ"""
    POISON = "poison"    # 毒
    PARALYSIS = "paralysis"  # 麻痺
    SLEEP = "sleep"      # 睡眠
    CONFUSION = "confusion"  # 混乱
    SILENCE = "silence"  # 沈黙


@dataclass
class StatusCondition:
    """状態異常条件"""
    effect: StatusEffect
    duration: int  # ターン数
    value: int = 0  # 効果値（毒のダメージなど）
    
    def __str__(self):
        return f"{self.effect.value}({self.duration}ターン)"


# === 武器システム ===

class WeaponType(Enum):
    """武器タイプ"""
    SWORD = "sword"    # 剣
    BOW = "bow"        # 弓矢
    AXE = "axe"        # 斧
    HAMMER = "hammer"  # ハンマー


@dataclass
class WeaponEffect:
    """武器の特殊効果"""
    # 基本ステータス変更
    attack_bonus: int = 0
    
    # 属性攻撃
    element: Optional[Element] = None
    element_damage: int = 0
    
    # 種族特攻
    effective_races: Set[Race] = field(default_factory=set)
    race_damage_multiplier: float = 1.5  # 特攻倍率
    
    # 状態異常付与
    status_effects: List[StatusCondition] = field(default_factory=list)
    status_chance: float = 0.0  # 状態異常発生確率
    
    # クリティカル率
    critical_rate_bonus: float = 0.0  # クリティカル率上昇
    
    def __str__(self):
        effects = []
        if self.attack_bonus > 0:
            effects.append(f"攻撃力+{self.attack_bonus}")
        if self.element:
            effects.append(f"{self.element.value}属性+{self.element_damage}")
        if self.effective_races:
            races = [race.value for race in self.effective_races]
            effects.append(f"特攻: {', '.join(races)}")
        if self.status_effects:
            effects.append(f"状態異常: {', '.join(str(e) for e in self.status_effects)}")
        if self.critical_rate_bonus > 0:
            effects.append(f"クリティカル+{self.critical_rate_bonus:.1%}")
        
        return " / ".join(effects) if effects else "特殊効果なし"


@dataclass(frozen=True)
class Weapon(Item):
    """武器クラス"""
    weapon_type: WeaponType
    effect: WeaponEffect
    rarity: str = "common"  # common, rare, epic, legendary
    
    def calculate_damage(self, base_attack: int, target_race: Optional[Race] = None) -> int:
        """ダメージ計算"""
        total_damage = base_attack + self.effect.attack_bonus
        
        # 種族特攻チェック
        if target_race and target_race in self.effect.effective_races:
            total_damage = int(total_damage * self.effect.race_damage_multiplier)
        
        # 属性ダメージ追加
        if self.effect.element and self.effect.element != Element.PHYSICAL:
            total_damage += self.effect.element_damage
        
        return total_damage
    
    def get_critical_rate(self) -> float:
        """クリティカル率を取得"""
        return self.effect.critical_rate_bonus
    
    def __str__(self):
        return f"{self.item_id} ({self.weapon_type.value}) - {self.description} [{self.effect}]"


# === 防具システム ===

class ArmorType(Enum):
    """防具タイプ"""
    HELMET = "helmet"    # ヘルメット
    ARMOR = "armor"      # アーマー
    SHOES = "shoes"      # シューズ
    GLOVES = "gloves"    # グローブ


class DamageType(Enum):
    """ダメージタイプ"""
    PHYSICAL = "physical"  # 物理ダメージ
    MAGICAL = "magical"    # 魔法ダメージ


@dataclass
class ArmorEffect:
    """防具の特殊効果"""
    # 基本ステータス変更
    defense_bonus: int = 0
    
    # 反撃効果
    counter_damage: int = 0
    counter_chance: float = 0.0  # 反撃発生確率
    
    # 状態異常耐性
    status_resistance: Dict[StatusEffect, float] = field(default_factory=dict)  # 状態異常への耐性率
    
    # ダメージ軽減
    damage_reduction: Dict[DamageType, float] = field(default_factory=dict)  # ダメージタイプ別軽減率
    
    # 回避率
    evasion_bonus: float = 0.0  # 回避率上昇
    
    # 移動速度
    speed_bonus: int = 0  # 素早さ上昇
    
    def __str__(self):
        effects = []
        if self.defense_bonus > 0:
            effects.append(f"防御力+{self.defense_bonus}")
        if self.counter_damage > 0:
            effects.append(f"反撃({self.counter_chance:.1%})")
        if self.status_resistance:
            resistances = [f"{k.value}耐性{v:.1%}" for k, v in self.status_resistance.items()]
            effects.append(f"耐性: {', '.join(resistances)}")
        if self.damage_reduction:
            reductions = [f"{k.value}軽減{v:.1%}" for k, v in self.damage_reduction.items()]
            effects.append(f"軽減: {', '.join(reductions)}")
        if self.evasion_bonus > 0:
            effects.append(f"回避+{self.evasion_bonus:.1%}")
        if self.speed_bonus > 0:
            effects.append(f"素早さ+{self.speed_bonus}")
        
        return " / ".join(effects) if effects else "特殊効果なし"


@dataclass(frozen=True)
class Armor(Item):
    """防具クラス"""
    armor_type: ArmorType
    effect: ArmorEffect
    rarity: str = "common"  # common, rare, epic, legendary
    
    def calculate_defense_bonus(self) -> int:
        """防御力ボーナスを計算"""
        return self.effect.defense_bonus
    
    def get_damage_reduction(self, damage_type: DamageType) -> float:
        """ダメージ軽減率を取得"""
        return self.effect.damage_reduction.get(damage_type, 0.0)
    
    def get_status_resistance(self, status: StatusEffect) -> float:
        """状態異常耐性を取得"""
        return self.effect.status_resistance.get(status, 0.0)
    
    def get_counter_chance(self) -> float:
        """反撃確率を取得"""
        return self.effect.counter_chance
    
    def get_counter_damage(self) -> int:
        """反撃ダメージを取得"""
        return self.effect.counter_damage
    
    def get_evasion_bonus(self) -> float:
        """回避率ボーナスを取得"""
        return self.effect.evasion_bonus
    
    def get_speed_bonus(self) -> int:
        """素早さボーナスを取得"""
        return self.effect.speed_bonus
    
    def __str__(self):
        return f"{self.item_id} ({self.armor_type.value}) - {self.description} [{self.effect}]"


# === 装備セット ===

@dataclass
class EquipmentSet:
    """装備セット"""
    weapon: Optional[Weapon] = None
    helmet: Optional[Armor] = None
    armor: Optional[Armor] = None
    shoes: Optional[Armor] = None
    gloves: Optional[Armor] = None
    
    def get_total_attack_bonus(self) -> int:
        """総攻撃力ボーナス"""
        total = 0
        if self.weapon:
            total += self.weapon.effect.attack_bonus
        return total
    
    def get_total_defense_bonus(self) -> int:
        """総防御力ボーナス"""
        total = 0
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                total += armor.effect.defense_bonus
        return total
    
    def get_total_speed_bonus(self) -> int:
        """総素早さボーナス"""
        total = 0
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                total += armor.effect.speed_bonus
        return total
    
    def get_total_critical_rate(self) -> float:
        """総クリティカル率"""
        if self.weapon:
            return self.weapon.get_critical_rate()
        return 0.0
    
    def get_total_evasion_rate(self) -> float:
        """総回避率"""
        total = 0.0
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                total += armor.get_evasion_bonus()
        return min(total, 0.95)  # 最大95%
    
    def get_equipped_weapons(self) -> List[Weapon]:
        """装備中の武器リスト"""
        return [self.weapon] if self.weapon else []
    
    def get_equipped_armors(self) -> List[Armor]:
        """装備中の防具リスト"""
        armors = []
        for armor in [self.helmet, self.armor, self.shoes, self.gloves]:
            if armor:
                armors.append(armor)
        return armors
    
    def equip_weapon(self, weapon: Weapon) -> Optional[Weapon]:
        """武器を装備（前の武器を返す）"""
        previous = self.weapon
        self.weapon = weapon
        return previous
    
    def equip_armor(self, armor: Armor) -> Optional[Armor]:
        """防具を装備（前の防具を返す）"""
        previous = None
        if armor.armor_type == ArmorType.HELMET:
            previous = self.helmet
            self.helmet = armor
        elif armor.armor_type == ArmorType.CHEST:
            previous = self.armor
            self.armor = armor
        elif armor.armor_type == ArmorType.SHOES:
            previous = self.shoes
            self.shoes = armor
        elif armor.armor_type == ArmorType.GLOVES:
            previous = self.gloves
            self.gloves = armor
        return previous
    
    def unequip_weapon(self) -> Optional[Weapon]:
        """武器を外す"""
        weapon = self.weapon
        self.weapon = None
        return weapon
    
    def unequip_armor(self, armor_type: ArmorType) -> Optional[Armor]:
        """防具を外す"""
        if armor_type == ArmorType.HELMET:
            armor = self.helmet
            self.helmet = None
            return armor
        elif armor_type == ArmorType.CHEST:
            armor = self.armor
            self.armor = None
            return armor
        elif armor_type == ArmorType.SHOES:
            armor = self.shoes
            self.shoes = None
            return armor
        elif armor_type == ArmorType.GLOVES:
            armor = self.gloves
            self.gloves = None
            return armor
        return None
    
    def __str__(self):
        equipped = []
        if self.weapon:
            equipped.append(f"武器: {self.weapon.item_id}")
        if self.helmet:
            equipped.append(f"頭: {self.helmet.item_id}")
        if self.armor:
            equipped.append(f"体: {self.armor.item_id}")
        if self.shoes:
            equipped.append(f"足: {self.shoes.item_id}")
        if self.gloves:
            equipped.append(f"手: {self.gloves.item_id}")
        
        return "装備: " + ", ".join(equipped) if equipped else "装備なし" 