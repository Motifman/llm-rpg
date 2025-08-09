from typing import Optional, TYPE_CHECKING, List
from game.player.inventory import Inventory
from game.player.equipment_set import EquipmentSet
from game.player.status import Status
from game.item.item import Item
from game.item.equipment_item import Weapon, Armor
from game.enums import Role, EquipmentSlot, StatusEffectType, PlayerState
from game.player.appearance import AppearanceSet
from game.item.item import AppearanceItem

# 型ヒントの遅延インポート
if TYPE_CHECKING:
    from game.action.actions.item_action import ItemUseResult, ConsumableItem, ItemEffect
    from game.action.actions.equipment_action import EquipItemResult, UnequipItemResult


class Player:
    """プレイヤークラス"""
    
    def __init__(self, player_id: str, name: str, role: Role):
        self.player_id = player_id
        self.name = name
        self.role = role
        self.current_spot_id = None
        self.inventory = Inventory()
        self.equipment = EquipmentSet()
        self.status = Status()
        self.player_state = PlayerState.NORMAL
        self.appearance = AppearanceSet()
    
    # ===== 基本情報 =====
    def get_player_id(self) -> str:
        """プレイヤーIDを取得"""
        return self.player_id
    
    def get_name(self) -> str:
        """プレイヤー名を取得"""
        return self.name

    def get_current_spot_id(self) -> str:
        """現在のスポットIDを取得"""
        return self.current_spot_id
    
    def set_current_spot_id(self, spot_id: str):
        """現在のスポットIDを設定"""
        self.current_spot_id = spot_id
    
    def get_role(self) -> Role:
        """ロールを取得"""
        return self.role
    
    def set_role(self, role: Role):
        """ロールを設定"""
        self.role = role
    
    def is_role(self, role: Role) -> bool:
        """指定されたロールかどうか"""
        return self.role == role
    
    # ===== 状態管理 =====
    def get_player_state(self) -> PlayerState:
        """プレイヤーの状態を取得"""
        return self.player_state
    
    def set_player_state(self, state: PlayerState):
        """プレイヤーの状態を設定"""
        self.player_state = state
    
    def is_in_state(self, state: PlayerState) -> bool:
        """指定された状態かどうか"""
        return self.player_state == state
    
    def is_in_normal_state(self) -> bool:
        """通常状態かどうか"""
        return self.player_state == PlayerState.NORMAL
    
    def is_in_conversation_state(self) -> bool:
        """会話状態かどうか"""
        return self.player_state == PlayerState.CONVERSATION
        
    def is_in_sns_state(self) -> bool:
        """SNS状態かどうか"""
        return self.player_state == PlayerState.SNS
        
    def is_in_battle_state(self) -> bool:
        """戦闘状態かどうか"""
        return self.player_state == PlayerState.BATTLE
        
    def is_in_trading_state(self) -> bool:
        """取引状態かどうか"""
        return self.player_state == PlayerState.TRADING

    # ===== 見た目（服飾）管理 =====
    def set_base_appearance(self, description: str):
        """服飾とは独立した基本の容姿テキストを設定"""
        self.appearance.set_base_description(description)

    def get_appearance_text(self) -> str:
        """現在の見た目（基本容姿 + 服飾）を取得"""
        return self.appearance.get_appearance_description()

    def equip_clothing(self, item_id: str) -> Optional[str]:
        """服飾アイテムを装着（スロットはアイテムが保持）。
        インベントリから取り出し、既存はインベントリに戻す。
        戻り値: 外したアイテムID（存在しなければNone）
        エラー処理: AppearanceItemであること、slotが適切なEnumであること
        """
        item = self.inventory.get_item_by_id(item_id)
        if item is None or not isinstance(item, AppearanceItem):
            return None
        slot = getattr(item, 'slot', None)
        # Enum妥当性
        try:
            from game.enums import AppearanceSlot  # 局所インポートで循環回避
            if not isinstance(slot, AppearanceSlot):
                return None
        except Exception:
            return None

        removed_count = self.inventory.remove_item_by_id(item.item_id, 1)
        if removed_count <= 0:
            return None

        previous = self.appearance.equip(slot, item)
        if previous:
            self.inventory.add_item(previous)
            return previous.item_id
        return None

    def unequip_clothing(self, slot: "AppearanceSlot") -> Optional[str]:
        """服飾アイテムを外し、インベントリへ戻す。戻り値: 外したアイテムID"""
        previous = self.appearance.unequip(slot)
        if previous:
            self.inventory.add_item(previous)
            return previous.item_id
        return None
    
    # ===== インベントリ管理 =====
    def get_inventory(self) -> Inventory:
        """インベントリを取得"""
        return self.inventory
    
    def set_inventory(self, inventory: Inventory):
        """インベントリを設定"""
        self.inventory = inventory
    
    def add_item(self, item: Item):
        """アイテムを追加"""
        self.inventory.add_item(item)
    
    def remove_item(self, item_id: str, count: int = 1) -> int:
        """アイテムを削除"""
        return self.inventory.remove_item_by_id(item_id, count=count)
    
    def has_item(self, item_id: str) -> bool:
        """アイテムを所持しているか"""
        return self.inventory.has_item(item_id)
    
    def get_inventory_items(self) -> List[Item]:
        """インベントリ内のアイテム一覧を取得"""
        return self.inventory.get_items()
    
    def get_inventory_item_count(self, item_id: str) -> int:
        """インベントリ内のアイテム数を取得"""
        return self.inventory.get_item_count(item_id)
    
    def get_all_equipment_item_ids(self) -> List[str]:
        """装備可能アイテムのID一覧を取得"""
        return self.inventory.get_all_equipment_item_ids()
    
    def get_all_consumable_item_ids(self) -> List[str]:
        """消費可能アイテムのID一覧を取得"""
        return self.inventory.get_all_consumable_item_ids()
    
    # ===== 装備管理 =====
    def get_equipment(self) -> EquipmentSet:
        """装備セットを取得"""
        return self.equipment
    
    def set_equipment(self, equipment: EquipmentSet):
        """装備セットを設定"""
        self.equipment = equipment
    
    def equip_item(self, item_id: str) -> 'EquipItemResult':
        """アイテムを装備"""
        from game.action.actions.equipment_action import EquipItemResult
        
        item = self.inventory.get_item_by_id(item_id)
        if item is None:
            return EquipItemResult(False, "アイテムが見つかりません", str(self.equipment), item_id, None)
        
        self.inventory.remove_item_by_id(item.item_id, 1)
        if isinstance(item, Weapon):
            old_weapon = self.equipment.equip_weapon(item)
            if old_weapon:
                self.inventory.add_item(old_weapon)
            return EquipItemResult(True, "武器を装備しました", str(self.equipment), item.item_id, old_weapon.item_id if old_weapon else None)
        elif isinstance(item, Armor):
            old_armor = self.equipment.equip_armor(item)
            if old_armor:
                self.inventory.add_item(old_armor)
            return EquipItemResult(True, "防具を装備しました", str(self.equipment), item.item_id, old_armor.item_id if old_armor else None)
        else:
            return EquipItemResult(False, "アイテムを装備できません", str(self.equipment), item.item_id, None)
    
    def unequip_slot(self, slot: EquipmentSlot) -> 'UnequipItemResult':
        """スロットから装備を外す"""
        from game.action.actions.equipment_action import UnequipItemResult
        
        item = self.equipment.unequip_slot(slot)
        if item:
            self.inventory.add_item(item)
            slot_name = self.equipment.get_slot_name(slot)
            return UnequipItemResult(True, f"{slot_name}を外しました", str(self.equipment), item.item_id)
        else:
            slot_name = self.equipment.get_slot_name(slot)
            return UnequipItemResult(False, f"{slot_name}を装備していないため外せません", str(self.equipment), None)
    
    def get_equipped_slots(self) -> List[EquipmentSlot]:
        """装備中のスロット一覧を取得"""
        return self.equipment.get_equipped_slots()
    
    def get_available_equipment_slots(self) -> List[EquipmentSlot]:
        """利用可能な装備スロット一覧を取得"""
        return self.equipment.get_available_slots()
    
    def get_equipped_item(self, slot: EquipmentSlot) -> Optional[Item]:
        """指定スロットの装備アイテムを取得"""
        return self.equipment.get_equipped_item(slot)
    
    def get_equipped_weapon(self) -> Optional[Weapon]:
        """装備中の武器を取得"""
        return self.equipment.get_equipped_weapon()
    
    def get_equipped_armors(self) -> List[Armor]:
        """装備中の防具一覧を取得"""
        return self.equipment.get_equipped_armors()
    
    # ===== ステータス管理（基本値） =====
    def get_status(self) -> Status:
        """ステータスを取得"""
        return self.status
    
    def set_status(self, status: Status):
        """ステータスを設定"""
        self.status = status
    
    def get_hp(self) -> int:
        """現在のHPを取得"""
        return self.status.get_hp()
    
    def get_mp(self) -> int:
        """現在のMPを取得"""
        return self.status.get_mp()
    
    def get_max_hp(self) -> int:
        """最大HPを取得"""
        return self.status.get_max_hp()
    
    def get_max_mp(self) -> int:
        """最大MPを取得"""
        return self.status.get_max_mp()
    
    def get_base_attack(self) -> int:
        """基本攻撃力を取得（装備ボーナスなし）"""
        return self.status.get_base_attack()
    
    def get_base_defense(self) -> int:
        """基本防御力を取得（装備ボーナスなし）"""
        return self.status.get_base_defense()
    
    def get_base_speed(self) -> int:
        """基本素早さを取得（装備ボーナスなし）"""
        return self.status.get_base_speed()
    
    def get_base_critical_rate(self) -> float:
        """基本クリティカル率を取得"""
        return self.status.get_critical_rate()
    
    def get_base_evasion_rate(self) -> float:
        """基本回避率を取得"""
        return self.status.get_evasion_rate()
    
    # ===== 装備ボーナス込みのステータス値取得 =====
    def get_attack(self) -> int:
        """攻撃力を取得（装備ボーナス込み）"""
        base_attack = self.get_base_attack()
        equipment_bonuses = self.equipment.get_equipment_bonuses()
        return base_attack + equipment_bonuses['attack_bonus']
    
    def get_defense(self) -> int:
        """防御力を取得（装備ボーナス込み）"""
        base_defense = self.get_base_defense()
        equipment_bonuses = self.equipment.get_equipment_bonuses()
        return base_defense + equipment_bonuses['defense_bonus']
    
    def get_speed(self) -> int:
        """素早さを取得（装備ボーナス込み）"""
        base_speed = self.get_base_speed()
        equipment_bonuses = self.equipment.get_equipment_bonuses()
        return base_speed + equipment_bonuses['speed_bonus']
    
    def get_critical_rate(self) -> float:
        """クリティカル率を取得（装備ボーナス込み）"""
        base_critical_rate = self.get_base_critical_rate()
        equipment_bonuses = self.equipment.get_equipment_bonuses()
        return base_critical_rate + equipment_bonuses['critical_rate']
    
    def get_evasion_rate(self) -> float:
        """回避率を取得（装備ボーナス込み）"""
        base_evasion_rate = self.get_base_evasion_rate()
        equipment_bonuses = self.equipment.get_equipment_bonuses()
        return base_evasion_rate + equipment_bonuses['evasion_rate']
    
    def get_status_resistance(self, status_effect_type: StatusEffectType) -> float:
        """状態異常耐性を取得（装備ボーナス込み）"""
        equipment_bonuses = self.equipment.get_equipment_bonuses()
        return equipment_bonuses['status_resistance'].get(status_effect_type, 0.0)
    
    # ===== お金・経験値管理 =====
    def get_gold(self) -> int:
        """所持金を取得"""
        return self.status.get_gold()
    
    def add_gold(self, amount: int):
        """所持金を追加"""
        self.status.add_gold(amount)
    
    def get_experience_points(self) -> int:
        """経験値を取得"""
        return self.status.get_experience_points()
    
    def add_experience_points(self, amount: int):
        """経験値を追加"""
        self.status.add_experience_points(amount)
    
    def get_level(self) -> int:
        """レベルを取得"""
        return self.status.get_level()
    
    def set_level(self, level: int):
        """レベルを設定"""
        self.status.set_level(level)
    
    # ===== 状態異常管理 =====
    def has_status_condition(self, status_effect_type: StatusEffectType) -> bool:
        """状態異常を持っているかどうか"""
        return self.status.has_status_effect_type(status_effect_type)
    
    def process_status_effects(self):
        """状態異常を処理"""
        self.status.process_status_effects()
    
    # ===== アイテム使用 =====
    def use_item(self, item_id: str) -> 'ItemUseResult':
        """アイテムを使用"""
        from game.action.actions.item_action import ItemUseResult
        from game.item.consumable_item import ConsumableItem
        from game.item.item_effect import ItemEffect
        
        item = self.inventory.get_item_by_id(item_id)
        if item is None:
            return ItemUseResult(False, "アイテムが見つかりません", item_id)
        
        if not isinstance(item, ConsumableItem):
            return ItemUseResult(False, "アイテムが使用できません", item_id)
        
        if not item.can_consume(self):
            return ItemUseResult(False, "アイテムが使用できません", item_id)
        
        status_before = self.get_current_status_snapshot()
        
        self.inventory.remove_item(item)
        self.status.apply_item_effect(item.effect)
        
        status_after = self.get_current_status_snapshot()
        
        return ItemUseResult(
            success=True,
            message="アイテムを使用しました",
            item_id=item_id,
            effect=item.effect,
            status_before=status_before,
            status_after=status_after
        )
    
    def preview_item_effect(self, item_id: str) -> Optional['ItemEffect']:
        """アイテムの効果をプレビュー"""
        from game.item.consumable_item import ConsumableItem
        from game.item.item_effect import ItemEffect
        
        item = self.inventory.get_item_by_id(item_id)
        if item is None or not isinstance(item, ConsumableItem):
            return None
        return item.effect
    
    # ===== 戦闘関連 =====
    def is_defending(self) -> bool:
        """防御状態かどうか"""
        return self.status.is_defending()

    def set_defending(self, defending: bool):
        """防御状態を設定"""
        self.status.set_defending(defending)
        
    def take_damage(self, damage: int):
        """ダメージを受ける"""
        self.status.add_hp(-damage)

    def is_alive(self) -> bool:
        """生存しているかどうか"""
        return self.status.is_alive()
    
    # ===== ユーティリティ =====
    def get_current_status_snapshot(self) -> dict:
        """現在のステータスのスナップショットを取得"""
        return {
            'hp': self.get_hp(),
            'mp': self.get_mp(),
            'max_hp': self.get_max_hp(),
            'max_mp': self.get_max_mp(),
            'base_attack': self.get_base_attack(),
            'base_defense': self.get_base_defense(),
            'base_speed': self.get_base_speed(),
            'attack': self.get_attack(),
            'defense': self.get_defense(),
            'speed': self.get_speed(),
            'critical_rate': self.get_critical_rate(),
            'evasion_rate': self.get_evasion_rate(),
            'gold': self.get_gold(),
            'experience_points': self.status.get_experience_points()
        }
    
    def get_status_summary(self) -> str:
        """ステータスの要約を取得"""
        return self.status.get_status_summary() 