from abc import ABC
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.monster.monster_enum import Race
from src.domain.battle.battle_enum import Element


class CombatEntity(ABC):
    """戦闘エンティティの基底クラス - PlayerとMonsterの共通機能"""
    
    def __init__(
        self,
        name: str,
        race: Race,
        element: Element,
        current_spot_id: int,
        base_status: BaseStatus,
        dynamic_status: DynamicStatus,
    ):
        self._name = name
        self._race = race
        self._element = element
        self._current_spot_id = current_spot_id
        self._base_status = base_status
        self._dynamic_status = dynamic_status
    
    # ===== 基本プロパティ =====
    @property
    def name(self) -> str:
        """名前を取得"""
        return self._name
    
    @property
    def race(self) -> Race:
        """種族を取得"""
        return self._race
    
    @property
    def element(self) -> Element:
        """属性を取得"""
        return self._element
    
    @property
    def current_spot_id(self) -> int:
        """現在のスポットIDを取得"""
        return self._current_spot_id
    
    # ===== ステータスプロパティ =====
    @property
    def attack(self) -> int:
        """攻撃力を取得"""
        return self._base_status.attack
    
    @property
    def defense(self) -> int:
        """防御力を取得"""
        return self._base_status.defense
    
    @property
    def speed(self) -> int:
        """素早さを取得"""
        return self._base_status.speed
    
    @property
    def hp(self) -> int:
        """HPを取得"""
        return self._dynamic_status.hp
    
    @property
    def mp(self) -> int:
        """MPを取得"""
        return self._dynamic_status.mp
    
    @property
    def max_hp(self) -> int:
        """最大HPを取得"""
        return self._dynamic_status.max_hp
    
    @property
    def max_mp(self) -> int:
        """最大MPを取得"""
        return self._dynamic_status.max_mp
    
    @property
    def critical_rate(self) -> float:
        """クリティカル率を取得"""
        return self._base_status.critical_rate
    
    @property
    def evasion_rate(self) -> float:
        """回避率を取得"""
        return self._base_status.evasion_rate
    
    # ===== 戦闘関連メソッド =====
    def take_damage(self, damage: int):
        """ダメージを受ける"""
        assert damage > 0, "damage must be greater than 0"
        self._dynamic_status.take_damage(damage)
    
    def heal(self, amount: int):
        """回復"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.heal(amount)
    
    def recover_mp(self, amount: int):
        """MP回復"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.recover_mp(amount)
    
    def consume_mp(self, amount: int):
        """MPを消費"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.consume_mp(amount)
    
    def can_consume_mp(self, amount: int) -> bool:
        """MPが足りるかどうか"""
        return self._dynamic_status.can_consume_mp(amount)
    
    def is_alive(self) -> bool:
        """生存しているかどうか"""
        return self._dynamic_status.is_alive()
    
    def is_defending(self) -> bool:
        """防御状態かどうか"""
        return self._dynamic_status.defending
    
    def defend(self):
        """防御状態にする"""
        self._dynamic_status.defend()
    
    def un_defend(self):
        """防御解除"""
        self._dynamic_status.un_defend()
    
    # ===== スポット移動 =====
    def set_current_spot_id(self, spot_id: int):
        """現在のスポットIDを設定"""
        self._current_spot_id = spot_id
