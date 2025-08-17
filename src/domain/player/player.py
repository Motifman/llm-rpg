from typing import List, Optional, Union
from typing_extensions import deprecated
from src.domain.item.item_effect import ItemEffect
from src.domain.item.item_enum import ItemType
from src.domain.item.item import Item
from src.domain.item.unique_item import UniqueItem
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.player_enum import Role, PlayerState
from src.domain.trade.trade import TradeItem
from src.domain.conversation.message import Message
from src.domain.conversation.message_box import MessageBox
from src.domain.battle.battle_enum import StatusEffectType, Element
from src.domain.battle.status_effect_result import StatusEffectResult
from src.domain.battle.combat_entity import CombatEntity
from src.domain.monster.monster_enum import Race


class Player(CombatEntity):
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
        equipment_set: EquipmentSet,
        message_box: MessageBox,
        race: Race = Race.HUMAN,
        element: Element = Element.NEUTRAL,
    ):
        # 基底クラスの初期化
        super().__init__(name, race, element, current_spot_id, base_status, dynamic_status)
        
        # プレイヤー固有の属性
        self._player_id = player_id
        self._role = role
        self._player_state = PlayerState.NORMAL
        self._inventory = inventory
        self._equipment = equipment_set
        self._message_box = message_box
        # self._appearance = AppearanceSet()  # 将来実装
    
    # ===== 基本情報 =====
    @property
    def player_id(self) -> int:
        """プレイヤーIDを取得"""
        return self._player_id
    
    @property
    def role(self) -> Role:
        """ロールを取得"""
        return self._role
    
    @property
    def player_state(self) -> PlayerState:
        """プレイヤーの状態を取得"""
        return self._player_state
    
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
    
    @property
    def level(self) -> int:
        """レベルを取得"""
        return self._dynamic_status.level
    
    @property
    def gold(self) -> int:
        """所持金を取得"""
        return self._dynamic_status.gold
    
    @property
    def exp(self) -> int:
        """経験値を取得"""
        return self._dynamic_status.exp

    # ===== ビジネスロジックの実装 =====
    # ===== プレイヤー固有のステータス関連メソッド =====
        
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
    
    def _remove_stackable(self, item: Item, count: int):
        """スタック可能アイテムを削除"""
        assert count > 0, "count must be greater than 0"
        self._inventory.remove_stackable(item.item_id, count)
    
    def _remove_unique(self, item: UniqueItem):
        """ユニークアイテムを削除"""
        self._inventory.remove_unique(item.unique_item_id)
    
    def use_item(self, item: Item, count: int = 1):
        """アイテムを使用"""
        assert count > 0, "count must be greater than 0"
        if item.item_type != ItemType.CONSUMABLE:
            raise ValueError("Item is not consumable")
        if not self._inventory.has_stackable(item.item_id, count):
            raise ValueError("Player does not have enough items")
        self._inventory.remove_stackable(item.item_id, count)
        if item.item_effect is not None:
            self._apply_item_effect(item.item_effect, count)
    
    def _apply_item_effect(self, item_effect: ItemEffect, count: int):
        """アイテム効果を適用"""
        # HP・MP変化
        if item_effect.hp_delta > 0:
            self._dynamic_status.heal(item_effect.hp_delta * count)
        if item_effect.mp_delta > 0:
            self._dynamic_status.recover_mp(item_effect.mp_delta * count)
        
        # 所持金・経験値変化
        if item_effect.gold_delta > 0:
            self._dynamic_status.receive_gold(item_effect.gold_delta * count)
        if item_effect.exp_delta > 0:
            self._dynamic_status.receive_exp(item_effect.exp_delta * count)
        
        # 状態異常効果
        for status_effect in item_effect.temporary_effects:
            self._dynamic_status.add_status_effect(
                status_effect.effect_type, 
                status_effect.duration, 
                status_effect.value
            )
    
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
            self._remove_unique(unique_item)
        else:
            stackable_item = self._inventory.get_stackable(trade_item.item_id)
            if stackable_item is None:
                raise ValueError(f"Stackable item not found: {trade_item.item_id}")
            player.add_item(stackable_item, trade_item.count)
            self._remove_stackable(stackable_item, trade_item.count)
    
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
            from src.domain.item.item_enum import ItemType
            previous_equipment = None
            
            if unique_item.item.item_type == ItemType.HELMET:
                previous_equipment = self._equipment.equip_helmet(unique_item)
            elif unique_item.item.item_type == ItemType.CHEST:
                previous_equipment = self._equipment.equip_chest(unique_item)
            elif unique_item.item.item_type == ItemType.GLOVES:
                previous_equipment = self._equipment.equip_gloves(unique_item)
            elif unique_item.item.item_type == ItemType.SHOES:
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
        lines.append(f"HP: {self.hp}/{self.max_hp}")
        lines.append(f"MP: {self.mp}/{self.max_mp}")
        lines.append(f"所持金: {self.gold} G")
        lines.append(f"経験値: {self.exp}")
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

