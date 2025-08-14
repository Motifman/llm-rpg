from typing import List, Optional
from domain.item.item import Item
from domain.item.unique_item import UniqueItem
from domain.player.base_status import BaseStatus
from domain.player.dynamic_status import DynamicStatus
from domain.player.inventory import Inventory
from domain.player.enum import Role, PlayerState, StatusEffectType
from application.battle.dtos import StatusEffectDto


# TODO 装備の効果をのちに追加
class Player:
    """プレイヤークラス"""
    
    def __init__(
        self,
        player_id: int,
        name: str,
        role: Role,
        current_spot_id: int,
        base_status: BaseStatus,
        dynamic_status: DynamicStatus,
        inventory: Inventory,
    ):
        self._player_id = player_id
        self._name = name
        self._role = role
        self._player_state = PlayerState.NORMAL
        self._current_spot_id = current_spot_id
        self._base_status = base_status
        self._dynamic_status = dynamic_status
        self._inventory = inventory
        # あとで実装
        # self._equipment = EquipmentSet()
        # self._appearance = AppearanceSet()
    
    # ===== 基本情報 =====
    @property
    def player_id(self) -> int:
        """プレイヤーIDを取得"""
        return self._player_id
    
    @property
    def name(self) -> str:
        """プレイヤー名を取得"""
        return self._name
    
    @property
    def role(self) -> Role:
        """ロールを取得"""
        return self._role
    
    @property
    def player_state(self) -> PlayerState:
        """プレイヤーの状態を取得"""
        return self._player_state
    
    @property
    def current_spot_id(self) -> int:
        """現在のスポットIDを取得"""
        return self._current_spot_id
    
    @property
    def attack(self) -> int:
        """攻撃力を取得"""
        base = self._base_status.attack
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.ATTACK_UP)
        return base + effect_bonus
    
    @property
    def defense(self) -> int:
        """防御力を取得"""
        base = self._base_status.defense
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.DEFENSE_UP)
        return base + effect_bonus
    
    @property
    def speed(self) -> int:
        """素早さを取得"""
        base = self._base_status.speed
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.SPEED_UP)
        return base + effect_bonus

    # ===== ビジネスロジックの実装 =====
    # ===== ステータス =====
    def take_damage(self, damage: int):
        """ダメージを受ける"""
        assert damage > 0, "damage must be greater than 0"
        damage = max(0, damage - self.defense)
        self._dynamic_status.take_damage(damage)
    
    def heal(self, amount: int):
        """回復"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.heal(amount)
    
    def heal_status_effect(self, status_effect_type: StatusEffectType):
        """特定の状態異常を回復"""
        self._dynamic_status.remove_status_effect_by_type(status_effect_type)
    
    def add_status_effect(self, status_effect_type: StatusEffectType, duration: int, value: int):
        """状態異常を追加"""
        self._dynamic_status.add_status_effect(status_effect_type, duration, value)
    
    def has_status_effect(self, status_effect_type: StatusEffectType) -> bool:
        """特定の状態異常を持っているかどうか"""
        return self._dynamic_status.has_status_effect_type(status_effect_type)
    
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

    def process_status_effects_on_turn_start(self) -> List[StatusEffectDto]:
        """ターン開始時に実行し、該当する状態異常のメッセージを返す"""
        results: List[StatusEffectDto] = []
        if self.has_status_effect(StatusEffectType.PARALYSIS):
            results.append(StatusEffectDto(StatusEffectType.PARALYSIS, f"{self.name}は麻痺で動けない！"))
        if self.has_status_effect(StatusEffectType.SLEEP):
            results.append(StatusEffectDto(StatusEffectType.SLEEP, f"{self.name}は眠っていて行動できない…"))
        if self.has_status_effect(StatusEffectType.CONFUSION):
            damage = max(1, self.attack // 2)
            self._dynamic_status.take_damage(damage)
            results.append(StatusEffectDto(StatusEffectType.CONFUSION, f"{self.name}は混乱して自分を攻撃！ {damage}のダメージ"))
        return results

    def process_status_effects_on_turn_end(self) -> List[StatusEffectDto]:
        """ターン終了時に実行し、該当する状態異常のメッセージを返す"""
        results: List[StatusEffectDto] = []
        if self.has_status_effect(StatusEffectType.POISON):
            damage = self._dynamic_status.get_effect_damage(StatusEffectType.POISON)
            self._dynamic_status.take_damage(damage)
            results.append(StatusEffectDto(StatusEffectType.POISON, f"{self.name}は毒により{damage}のダメージを受けた"))
        if self.has_status_effect(StatusEffectType.BURN):
            damage = self._dynamic_status.get_effect_damage(StatusEffectType.BURN)
            self._dynamic_status.take_damage(damage)
            results.append(StatusEffectDto(StatusEffectType.BURN, f"{self.name}は火傷により{damage}のダメージを受けた"))
        if self.has_status_effect(StatusEffectType.BLESSING):
            bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.BLESSING)
            if bonus > 0:
                self._dynamic_status.heal(bonus)
                results.append(StatusEffectDto(StatusEffectType.BLESSING, f"{self.name}は加護により{bonus}回復した"))
        return results

    def progress_status_effects_on_turn_end(self) -> None:
        """ターン終了時に呼び出して、状態異常のターンを進める"""
        self._dynamic_status.decrease_status_effect_duration()
    
    def can_act(self) -> bool:
        """行動可能かどうか"""
        if self.has_status_effect(StatusEffectType.PARALYSIS):
            return False
        if self.has_status_effect(StatusEffectType.SLEEP):
            return False
        return self.is_alive() and not self.is_defending()
    
    def can_magic(self) -> bool:
        """魔法攻撃可能かどうか"""
        if self.has_status_effect(StatusEffectType.SILENCE):
            return False
        return self.is_alive() and not self.is_defending()
        
    def add_gold(self, amount: int):
        """所持金を追加"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.add_gold(amount)
    
    def spend_gold(self, amount: int):
        """所持金を支払う"""
        assert amount > 0, "amount must be greater than 0"
        assert self._dynamic_status.gold >= amount, "gold must be greater than or equal to amount"
        self._dynamic_status.add_gold(-amount)
    
    def add_exp(self, amount: int):
        """経験値を追加"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.add_exp(amount)
    
    def spend_exp(self, amount: int):
        """経験値を消費"""
        assert amount > 0, "amount must be greater than 0"
        assert self._dynamic_status.exp >= amount, "exp must be greater than or equal to amount"
        self._dynamic_status.add_exp(-amount)
        
    # ===== インベントリ =====
    def add_stackable_item(self, item: Item, count: int = 1):
        """スタック可能アイテムを追加"""
        self._inventory.add_stackable(item, count)
    
    def remove_stackable_item(self, item_id: int, count: int = 1):
        """スタック可能アイテムを削除"""
        self._inventory.remove_stackable(item_id, count)
    
    def has_stackable_item(self, item_id: int, at_least: int = 1) -> bool:
        """スタック可能アイテムを持っているかどうか"""
        return self._inventory.has_stackable(item_id, at_least)
    
    def add_unique_item(self, unique_item: UniqueItem):
        """ユニークアイテムを追加"""
        self._inventory.add_unique(unique_item)
    
    def remove_unique_item(self, unique_item_id: int):
        """ユニークアイテムを削除"""
        self._inventory.remove_unique(unique_item_id)
    
    def has_unique_item(self, unique_item_id: int) -> bool:
        """ユニークアイテムを持っているかどうか"""
        return self._inventory.has_unique(unique_item_id)
    
    def get_inventory_display(self) -> str:
        """インベントリの表示"""
        return self._inventory.get_inventory_display()