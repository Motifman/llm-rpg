from datetime import datetime
from typing import Optional
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.item.consumable_item import ConsumableItem
from src.domain.item.equipment_item import EquipmentItem
from src.domain.item.item_enum import ItemType
from src.domain.item.item_quantity import ItemQuantity
from src.domain.item.unique_item import UniqueItem
from src.domain.item.item_exception import ItemNotFoundException, ItemNotUsableException, ItemNotEquippableException
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.player_enum import Role, PlayerState
from src.domain.player.message import Message
from src.domain.player.message_box import MessageBox
from src.domain.player.gold import Gold
from src.domain.player.exp import Exp
from src.domain.player.conversation_events import PlayerSpokeEvent
from src.domain.trade.trade import TradeItem
from src.domain.trade.trade_exception import InsufficientItemsException, InsufficientGoldException, ItemNotTradeableException, InsufficientInventorySpaceException
from src.domain.battle.battle_enum import Element
from src.domain.battle.combat_entity import CombatEntity
from src.domain.monster.monster_enum import Race
from src.application.trade.contracts.commands import CreateTradeCommand


class Player(CombatEntity, AggregateRoot):
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
    
    # ===== 取引関連の振る舞いの実装 =====
    def prepare_trade_offer(self, command: CreateTradeCommand) -> TradeItem:
        """取引試行"""
        item = self._inventory.search_item(command.offered_item_id, command.offered_unique_id)
        if item is None:
            raise InsufficientItemsException(f"Item not found. item_id: {command.offered_item_id}, unique_id: {command.offered_unique_id}")
        # 取引可能かどうかをチェック
        if hasattr(item, 'is_tradeable'):
            # UniqueItemの場合
            if not item.is_tradeable:
                raise ItemNotTradeableException(f"Item is not tradeable. item_id: {command.offered_item_id}, unique_id: {command.offered_unique_id}")
        elif hasattr(item, 'item'):
            # ItemQuantityの場合
            if not item.item.is_tradeable:
                raise ItemNotTradeableException(f"Item is not tradeable. item_id: {command.offered_item_id}, unique_id: {command.offered_unique_id}")
        if command.offered_item_count is not None:
            if self._inventory.has_stackable(command.offered_item_id, command.offered_item_count):
                return TradeItem.stackable(command.offered_item_id, command.offered_item_count)
            else:
                raise InsufficientItemsException(f"Item not found. item_id: {command.offered_item_id}, count: {command.offered_item_count}")
        else:
            if self._inventory.has_unique(command.offered_unique_id):
                return TradeItem.unique(command.offered_item_id, command.offered_unique_id)
            else:
                raise InsufficientItemsException(f"Item not found. item_id: {command.offered_item_id}, unique_id: {command.offered_unique_id}")

    def release_item_for_trade(self, trade_item: TradeItem) -> ItemQuantity | UniqueItem:
        """取引を行ったときにアイテムを開放"""
        if trade_item.is_stackable() and self._inventory.has_stackable(trade_item.item_id, trade_item.count):
            item_released = self._inventory.remove_item(item_id=trade_item.item_id, quantity=trade_item.count)
            if item_released is None:
                raise InsufficientItemsException(f"Item not found. item_id: {trade_item.item_id}, count: {trade_item.count}")
            return item_released
        elif trade_item.is_unique() and self._inventory.has_unique(trade_item.unique_id):
            item_released = self._inventory.remove_item(unique_id=trade_item.unique_id)
            if item_released is None:
                raise InsufficientItemsException(f"Item not found. item_id: {trade_item.item_id}, unique_id: {trade_item.unique_id}")
            return item_released
        else:
            raise InsufficientItemsException(f"Item not found. item_id: {trade_item.item_id}, unique_id: {trade_item.unique_id}")
    
    def receive_item_for_trade(self, item: ItemQuantity | UniqueItem):
        """取引を行ったときにアイテムを受け取る"""
        if isinstance(item, ItemQuantity) or isinstance(item, UniqueItem):
            is_added = self._inventory.add_item(item)
            if not is_added:
                raise InsufficientInventorySpaceException(f"Inventory is full. item_id: {item.item_id}, unique_id: {item.unique_id}")
        else:
            raise ValueError(f"Invalid item type: {type(item)}")
    
    def pay_gold_for_trade(self, gold: Gold):
        """取引を行ったときに所持金を支払う"""
        if not self._dynamic_status.can_pay_gold(gold):
            raise InsufficientGoldException(f"Player does not have enough gold: {gold}")
        self._dynamic_status.pay_gold(gold)
    
    def receive_gold_for_trade(self, gold: Gold):
        """取引を行ったときに所持金を受け取る"""
        self.receive_gold(gold)
    
    # ===== アイテム関連の振る舞い =====
    def use_item(self, item_id: int, count: int = 1):
        """アイテムを使用"""
        item = self._inventory.search_item(item_id=item_id)
        if item is None:
            raise InsufficientItemsException(f"Item not found. item_id: {item_id}, count: {count}")
        
        # ItemQuantityの場合はitemプロパティをチェック
        if isinstance(item, ItemQuantity):
            if isinstance(item.item, ConsumableItem):
                if self._inventory.has_stackable(item_id, count):
                    used_item = self._inventory.remove_item(item_id=item_id, quantity=count)
                    # 指定した回数だけuseメソッドを呼ぶ
                    for _ in range(count):
                        used_item.item.use(self)
                else:
                    raise InsufficientItemsException(f"Item not found. item_id: {item_id}, count: {count}")
            else:
                raise ItemNotUsableException(f"Item is not usable. item_id: {item_id}")
        elif isinstance(item, ConsumableItem):
            if self._inventory.has_stackable(item_id, count):
                used_item = self._inventory.remove_item(item_id=item_id, quantity=count)
                # 指定した回数だけuseメソッドを呼ぶ
                for _ in range(count):
                    used_item.use(self)
            else:
                raise InsufficientItemsException(f"Item not found. item_id: {item_id}, count: {count}")
        else:
            raise ItemNotUsableException(f"Item is not usable. item_id: {item_id}")

    def receive_exp(self, exp: Exp):
        """経験値を受け取る"""
        self._dynamic_status.receive_exp(exp)
    
    def receive_gold(self, gold: Gold):
        """所持金を受け取る"""
        self._dynamic_status.receive_gold(gold)

    def level_up(self):
        """レベルアップ"""
        self._dynamic_status.level_up()
    
    # ===== 装備関連の振る舞い =====
    def equip_item_from_inventory(self, item_id: int, unique_id: int):
        """アイテムを装備"""
        item = self._inventory.search_item(item_id=item_id, unique_id=unique_id)
        if item is None:
            raise ItemNotFoundException(f"Item not found. item_id: {item_id}, unique_id: {unique_id}")
        if not isinstance(item, EquipmentItem):
            raise ItemNotEquippableException(f"Item is not equippable. item_id: {item_id}, unique_id: {unique_id}")
        self._inventory.remove_item(item_id=item_id, unique_id=unique_id)
        previous_equipment = self._equipment.equip_item(item)
        if previous_equipment is not None:
            self._inventory.add_item(previous_equipment)
    
    def unequip_item_to_inventory(self, item_type: ItemType):
        """アイテムを脱装"""
        item = self._equipment.unequip_item(item_type)
        if item is not None:
            self._inventory.add_item(item)

    def calculate_status(self) -> BaseStatus:
        """ステータスを計算"""
        return self._base_status + self._equipment.calculate_status()

    # ===== メッセージ関連の振る舞い =====
    def speak(self, content: str, recipient: Optional["Player"] = None):
        if recipient is not None:
            if self._player_id == recipient._player_id:
                raise ValueError("Cannot send message to yourself")
            if self._current_spot_id != recipient._current_spot_id:
                raise ValueError("Cannot send message to a player in a different spot")
            self.add_event(PlayerSpokeEvent.create(self._player_id, content, recipient._player_id))
        else:
            self.add_event(PlayerSpokeEvent.create(self._player_id, content))
    
    def receive_message(self, message: Message):
        """メッセージを受信"""
        self._message_box.append(message)

    def read_messages(self) -> str:
        """メッセージを既読にして表示"""
        messages = self._message_box.read_all()
        if len(messages) == 0:
            return ""
        return "\n".join([message.display() for message in messages])