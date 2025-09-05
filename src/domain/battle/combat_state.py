from dataclasses import dataclass
from typing import Dict, List, TYPE_CHECKING
from src.domain.battle.battle_enum import Element, Race, ParticipantType, StatusEffectType, BuffType
from src.domain.battle.constant import IF_DEFENDER_DEFENDING_MULTIPLIER as DEFENDER_DEFENDING_MULTIPLIER
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp

if TYPE_CHECKING:
    from src.domain.player.player import Player
    from src.domain.monster.monster import Monster


@dataclass(frozen=True)
class StatusEffectState:
    """状態異常の状態"""
    effect_type: StatusEffectType
    duration: int

    def __post_init__(self):
        if self.duration < 0:
            raise ValueError(f"duration must be non-negative. duration: {self.duration}")
    
    def with_turn_progression(self) -> "StatusEffectState":
        return StatusEffectState(self.effect_type, self.duration - 1)
    
    def is_expired(self) -> bool:
        return self.duration == 0


@dataclass(frozen=True)
class BuffState:
    """バフの状態"""
    buff_type: BuffType
    multiplier: float
    duration: int

    def __post_init__(self):
        if self.multiplier <= 0:
            raise ValueError(f"multiplier must be positive. multiplier: {self.multiplier}")
        if self.duration < 0:
            raise ValueError(f"duration must be non-negative. duration: {self.duration}")

    def with_turn_progression(self) -> "BuffState":
        return BuffState(self.buff_type, self.multiplier, self.duration - 1)
    
    def is_expired(self) -> bool:
        return self.duration == 0


@dataclass(frozen=True)
class CombatState:
    """戦闘中の状態"""
    # === 基本情報 ===
    entity_id: int
    participant_type: ParticipantType
    name: str
    race: Race
    element: Element
    
    # === 現在の状態（戦闘中に変化） ===
    current_hp: Hp
    current_mp: Mp
    
    # === 戦闘状態（戦闘中に変化） ===
    status_effects: Dict[StatusEffectType, StatusEffectState]
    buffs: Dict[BuffType, BuffState]
    is_defending: bool
    can_act: bool
    
    # === 基本ステータス（計算用、変化しない） ===
    attack: int
    defense: int
    speed: int
    critical_rate: float
    evasion_rate: float
    
    @classmethod
    def from_player(cls, player: "Player", player_id: int) -> "CombatState":
        """CombatEntityからCombatStateを生成"""
        base_status = player.calculate_status_including_equipment()
        return cls(
            entity_id=player_id,
            participant_type=ParticipantType.PLAYER,
            name=player.name,
            race=player.race,
            element=player.element,
            current_hp=player.hp,
            current_mp=player.mp,
            status_effects={},  # 戦闘開始時は空
            buffs={},
            is_defending=False,
            can_act=True,
            attack=base_status.attack,
            defense=base_status.defense,
            speed=base_status.speed,
            critical_rate=base_status.critical_rate,
            evasion_rate=base_status.evasion_rate,
        )
    
    @classmethod
    def from_monster(cls, monster: "Monster", monster_id: int) -> "CombatState":
        """CombatEntityからCombatStateを生成"""
        base_status = monster.calculate_status_including_equipment()
        hp = Hp(monster.max_hp, monster.max_hp)
        mp = Mp(monster.max_mp, monster.max_mp)
        return cls(
            entity_id=monster_id,
            participant_type=ParticipantType.MONSTER,
            name=monster.name,
            race=monster.race,
            element=monster.element,
            current_hp=hp,
            current_mp=mp,
            status_effects={},  # 戦闘開始時は空
            buffs={},
            is_defending=False,
            can_act=True,
            attack=base_status.attack,
            defense=base_status.defense,
            speed=base_status.speed,
            critical_rate=base_status.critical_rate,
            evasion_rate=base_status.evasion_rate,
        )
    
    # === 状態変更メソッド ===
    def with_hp_damaged(self, damage: int) -> "CombatState":
        """ダメージを受けた新しい状態"""
        new_hp = self.current_hp.damage(damage)
        return CombatState(**{**self.__dict__, 'current_hp': new_hp})
    
    def with_hp_healed(self, heal: int) -> "CombatState":
        """ヒールを受けた新しい状態"""
        new_hp = self.current_hp.heal(heal)
        return CombatState(**{**self.__dict__, 'current_hp': new_hp})
    
    def with_mp_consumed(self, mp: int) -> "CombatState":
        """MPを消費した新しい状態"""
        new_mp = self.current_mp.consumed(mp)
        return CombatState(**{**self.__dict__, 'current_mp': new_mp})
    
    def with_mp_healed(self, mp: int) -> "CombatState":
        """MPを回復した新しい状態"""
        new_mp = self.current_mp.heal(mp)
        return CombatState(**{**self.__dict__, 'current_mp': new_mp})
    
    def with_status_effect(self, effect: StatusEffectType, duration: int) -> "CombatState":
        """状態異常を追加した新しい状態"""
        new_effects = self.status_effects.copy()
        new_effects[effect] = StatusEffectState(effect, duration)
        return CombatState(**{**self.__dict__, 'status_effects': new_effects})
    
    def without_status_effect(self, effect: StatusEffectType) -> "CombatState":
        """状態異常を削除した新しい状態"""
        new_effects = self.status_effects.copy()
        new_effects.pop(effect)
        return CombatState(**{**self.__dict__, 'status_effects': new_effects})
    
    def with_buff(self, buff: BuffType, multiplier: float, duration: int) -> "CombatState":
        """バフを追加した新しい状態"""
        new_buffs = self.buffs.copy()
        new_buffs[buff] = BuffState(buff, multiplier, duration)
        return CombatState(**{**self.__dict__, 'buffs': new_buffs})
    
    def without_buff(self, buff: BuffType) -> "CombatState":
        """バフを削除した新しい状態"""
        new_buffs = self.buffs.copy()
        new_buffs.pop(buff)
        return CombatState(**{**self.__dict__, 'buffs': new_buffs})
    
    def with_turn_progression(self) -> "CombatState":
        """ターン進行による状態更新"""
        new_effects = {}
        for effect, status_effect_state in self.status_effects.items():
            new_status_effect_state = status_effect_state.with_turn_progression()
            if not new_status_effect_state.is_expired():
                new_effects[effect] = new_status_effect_state

        new_buffs = {}
        for buff, buff_state in self.buffs.items():
            new_buff_state = buff_state.with_turn_progression()
            if not new_buff_state.is_expired():
                new_buffs[buff] = new_buff_state
        return CombatState(**{**self.__dict__, 'status_effects': new_effects, 'buffs': new_buffs})
    
    def with_defend(self) -> "CombatState":
        """防御状態にした新しい状態"""
        return CombatState(**{**self.__dict__, 'is_defending': True})
    
    def without_defend(self) -> "CombatState":
        """防御状態を解除した新しい状態"""
        return CombatState(**{**self.__dict__, 'is_defending': False})
    
    # === 計算メソッド ===
    def calculate_current_attack(self) -> int:
        """現在の攻撃力を計算"""
        buff = self.buffs.get(BuffType.ATTACK, None)
        multiplier = buff.multiplier if buff else 1.0
        return int(self.attack * multiplier)
    
    def calculate_current_defense(self) -> int:
        """現在の防御力を計算"""
        buff = self.buffs.get(BuffType.DEFENSE, None)
        multiplier = buff.multiplier if buff else 1.0
        defense = self.defense * multiplier
        if self.is_defending:
            defense *= DEFENDER_DEFENDING_MULTIPLIER
        return int(defense)
    
    def calculate_current_speed(self) -> int:
        """現在の速度を計算"""
        buff = self.buffs.get(BuffType.SPEED, None)
        multiplier = buff.multiplier if buff else 1.0
        return int(self.speed * multiplier)
    
    def has_status_effect(self, effect: StatusEffectType) -> bool:
        """状態異常を持っているかどうか"""
        return effect in self.status_effects
    
    def get_status_effect_remaining_duration(self, effect: StatusEffectType) -> int:
        """状態異常の残りターン数を取得"""
        effect_state = self.status_effects.get(effect, None)
        return effect_state.duration if effect_state else 0
    
    def is_alive(self) -> bool:
        """生存判定"""
        return self.current_hp.is_alive()