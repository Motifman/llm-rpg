from typing import List, Optional, Union
from src.domain.item.item import Item
from src.domain.item.unique_item import UniqueItem
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.enum import Role, PlayerState, StatusEffectType
from src.domain.trade.trade import TradeItem
from src.application.battle.dtos import StatusEffectDto
from src.domain.conversation.message import Message
from src.domain.conversation.message_box import MessageBox


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
        equipment_set: Optional[EquipmentSet] = None,
        message_box: Optional[MessageBox] = None,
    ):
        self._player_id = player_id
        self._name = name
        self._role = role
        self._player_state = PlayerState.NORMAL
        self._current_spot_id = current_spot_id
        self._base_status = base_status
        self._dynamic_status = dynamic_status
        self._inventory = inventory
        self._equipment = equipment_set or EquipmentSet()
        self._message_box = message_box or MessageBox()
        # self._appearance = AppearanceSet()  # 将来実装
    
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
        """攻撃力を取得（ベース + 装備ボーナス + 状態異常ボーナス）"""
        base = self._base_status.attack
        equipment_bonus = self._equipment.get_attack_bonus()
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.ATTACK_UP)
        return base + equipment_bonus + effect_bonus
    
    @property
    def defense(self) -> int:
        """防御力を取得（ベース + 装備ボーナス + 状態異常ボーナス）"""
        base = self._base_status.defense
        equipment_bonus = self._equipment.get_defense_bonus()
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.DEFENSE_UP)
        return base + equipment_bonus + effect_bonus
    
    @property
    def speed(self) -> int:
        """素早さを取得（ベース + 装備ボーナス + 状態異常ボーナス）"""
        base = self._base_status.speed
        equipment_bonus = self._equipment.get_speed_bonus()
        effect_bonus = self._dynamic_status.get_effect_bonus(StatusEffectType.SPEED_UP)
        return base + equipment_bonus + effect_bonus

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
        
    def receive_gold(self, amount: int):
        """所持金を追加"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.receive_gold(amount)
    
    def pay_gold(self, amount: int):
        """所持金を支払う"""
        assert amount > 0, "amount must be greater than 0"
        assert self._dynamic_status.gold >= amount, "gold must be greater than or equal to amount"
        self._dynamic_status.pay_gold(amount)
    
    def can_pay_gold(self, amount: int) -> bool:
        """所持金が足りるかどうか"""
        return self._dynamic_status.can_pay_gold(amount)

    def receive_exp(self, amount: int):
        """経験値を追加"""
        assert amount > 0, "amount must be greater than 0"
        self._dynamic_status.receive_exp(amount)
    
    def pay_exp(self, amount: int):
        """経験値を消費"""
        assert amount > 0, "amount must be greater than 0"
        assert self._dynamic_status.exp >= amount, "exp must be greater than or equal to amount"
        self._dynamic_status.pay_exp(amount)
    
    def can_pay_exp(self, amount: int) -> bool:
        """経験値が足りるかどうか"""
        return self._dynamic_status.can_pay_exp(amount)
    
    def level_up(self):
        """レベルアップ"""
        self._dynamic_status.level_up()
    
    def level_is_above(self, level: int) -> bool:
        """指定したレベルより上かどうか"""
        return self._dynamic_status.level_is_above(level)
    
    # ===== インベントリ =====
    def add_item(self, item: Union[Item, UniqueItem], count: int = 1):
        """アイテムを追加"""
        assert count > 0, "count must be greater than 0"
        if isinstance(item, Item):
            self._inventory.add_stackable(item, count)
        elif isinstance(item, UniqueItem):
            self._inventory.add_unique(item)
        else:
            raise ValueError("Invalid item type")
    
    def remove_item(self, item_id: Optional[int] = None, count: Optional[int] = None, unique_item_id: Optional[int] = None):
        """アイテムを削除"""
        is_stackable = item_id is not None and count is not None
        is_unique = unique_item_id is not None
        assert is_stackable or is_unique, "item_id and count or unique_item_id must be provided"
        assert not (is_stackable and is_unique), "item_id and count or unique_item_id must not be provided at the same time"
        if is_stackable:
            assert count > 0, "count must be greater than 0"
            self._inventory.remove_stackable(item_id, count)
        else:
            self._inventory.remove_unique(unique_item_id)
    
    def get_stackable_item(self, item_id: int) -> Optional[Item]:
        """スタック可能アイテムを取得"""
        return self._inventory.get_stackable(item_id)
    
    def get_unique_item(self, unique_item_id: int) -> Optional[UniqueItem]:
        """ユニークアイテムを取得"""
        return self._inventory.get_unique(unique_item_id)
    
    def get_inventory_display(self) -> str:
        """インベントリの表示"""
        return self._inventory.get_inventory_display()

    def has_stackable_item(self, item_id: int, count: int = 1) -> bool:
        """スタック可能アイテムを持っているかどうか"""
        return self._inventory.has_stackable(item_id, count)
    
    def has_unique_item(self, unique_item_id: int) -> bool:
        """ユニークアイテムを持っているかどうか"""
        return self._inventory.has_unique(unique_item_id)

    # ===== 取引関連 =====
    def can_offer_item(self, trade_item: TradeItem) -> bool:
        """アイテムを取引できるかどうか"""
        if trade_item.unique_id is not None:
            return self.has_unique_item(trade_item.unique_id)
        else:
            return self.has_stackable_item(trade_item.item_id, trade_item.count)
    
    def transfer_item_to(self, player: "Player", trade_item: TradeItem):
        """アイテムを別のプレイヤーに移動"""
        if trade_item.unique_id is not None:
            unique_item = self._inventory.get_unique(trade_item.unique_id)
            if unique_item is None:
                raise ValueError(f"Unique item not found: {trade_item.unique_id}")
            player.add_item(unique_item)
            self._inventory.remove_unique(trade_item.unique_id)
        else:
            stackable_item = self._inventory.get_stackable(trade_item.item_id)
            if stackable_item is None:
                raise ValueError(f"Stackable item not found: {trade_item.item_id}")
            player.add_item(stackable_item, trade_item.count)
            self._inventory.remove_stackable(trade_item.item_id, trade_item.count)
    
    def transfer_gold_to(self, player: "Player", amount: int):
        """所持金を別のプレイヤーに移動"""
        if not self.can_pay_gold(amount):
            raise ValueError(f"Player does not have enough gold: {amount}")
        self.pay_gold(amount)
        player.receive_gold(amount)
    
    # ===== 装備 =====
    @property
    def equipment(self) -> EquipmentSet:
        """装備セットを取得"""
        return self._equipment
    
    def equip_item_from_inventory(self, unique_item_id: int) -> bool:
        """インベントリからアイテムを装備する
        
        Returns:
            bool: 装備に成功した場合True
        """
        unique_item = self._inventory.get_unique(unique_item_id)
        if not unique_item:
            return False
        
        try:
            # アイテムタイプに応じて装備
            from domain.item.enum import ItemType
            previous_equipment = None
            
            if unique_item.item.type == ItemType.HELMET:
                previous_equipment = self._equipment.equip_helmet(unique_item)
            elif unique_item.item.type == ItemType.CHEST:
                previous_equipment = self._equipment.equip_chest(unique_item)
            elif unique_item.item.type == ItemType.GLOVES:
                previous_equipment = self._equipment.equip_gloves(unique_item)
            elif unique_item.item.type == ItemType.SHOES:
                previous_equipment = self._equipment.equip_shoes(unique_item)
            else:
                return False  # 装備できないタイプ
            
            # インベントリから削除
            self._inventory.remove_unique(unique_item_id)
            
            # 外した装備があればインベントリに戻す
            if previous_equipment:
                self._inventory.add_unique(previous_equipment)
            
            return True
            
        except ValueError:
            return False  # 装備に失敗（破損など）
    
    def unequip_item_to_inventory(self, slot_type: str) -> bool:
        """装備を外してインベントリに戻す
        
        Args:
            slot_type: "helmet", "chest", "gloves", "shoes"のいずれか
            
        Returns:
            bool: 脱装に成功した場合True
        """
        removed_equipment = None
        
        if slot_type == "helmet":
            removed_equipment = self._equipment.unequip_helmet()
        elif slot_type == "chest":
            removed_equipment = self._equipment.unequip_chest()
        elif slot_type == "gloves":
            removed_equipment = self._equipment.unequip_gloves()
        elif slot_type == "shoes":
            removed_equipment = self._equipment.unequip_shoes()
        else:
            return False  # 無効なスロットタイプ
        
        if removed_equipment:
            self._inventory.add_unique(removed_equipment)
            return True
        
        return False  # 何も装備していなかった
    
    def get_equipment_display(self) -> str:
        """装備の表示"""
        return self._equipment.get_equipment_display()
    
    def get_full_status_display(self) -> str:
        """プレイヤーの全ステータス表示"""
        lines = [f"=== {self.name} ({self.role.value}) ==="]
        lines.append(f"HP: {self._dynamic_status.hp}/{self._dynamic_status.max_hp}")
        lines.append(f"所持金: {self._dynamic_status.gold} G")
        lines.append(f"経験値: {self._dynamic_status.exp}")
        lines.append("")
        lines.append("=== ステータス ===")
        lines.append(f"攻撃力: {self.attack} (ベース:{self._base_status.attack} + 装備:{self._equipment.get_attack_bonus()} + 効果:{self._dynamic_status.get_effect_bonus(StatusEffectType.ATTACK_UP)})")
        lines.append(f"防御力: {self.defense} (ベース:{self._base_status.defense} + 装備:{self._equipment.get_defense_bonus()} + 効果:{self._dynamic_status.get_effect_bonus(StatusEffectType.DEFENSE_UP)})")
        lines.append(f"素早さ: {self.speed} (ベース:{self._base_status.speed} + 装備:{self._equipment.get_speed_bonus()} + 効果:{self._dynamic_status.get_effect_bonus(StatusEffectType.SPEED_UP)})")
        lines.append("")
        lines.append(self.get_equipment_display())
        lines.append("")
        lines.append(self.get_inventory_display())
        
        return "\n".join(lines)

    # ===== メッセージ =====
    def receive_message(self, message: Message):
        """メッセージを受信"""
        self._message_box.append(message)
    
    def read_messages(self) -> str:
        """メッセージを既読にして表示"""
        messages = self._message_box.read_all()
        if len(messages) == 0:
            return ""
        return "\n".join([message.display() for message in messages])