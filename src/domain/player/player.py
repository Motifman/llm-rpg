from typing import Optional, TYPE_CHECKING, Dict
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
from src.domain.common.value_object import Exp, Gold, Level
from src.domain.player.conversation_events import PlayerSpokeEvent
from src.domain.trade.trade import TradeItem
from src.domain.trade.trade_exception import InsufficientItemsException, InsufficientGoldException, ItemNotTradeableException, InsufficientInventorySpaceException
from src.domain.battle.battle_enum import Element, Race
from src.domain.battle.action_deck import ActionDeck
from src.domain.battle.action_mastery import ActionMastery
from src.domain.battle.action_slot import ActionSlot

if TYPE_CHECKING:
    from src.domain.battle.combat_state import CombatState
else:
    from src.domain.battle.combat_state import CombatState
from src.application.trade.contracts.commands import CreateTradeCommand
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.spot.movement_events import PlayerMovedEvent
from src.domain.spot.spot_exception import PlayerAlreadyInSpotException
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp


class Player(AggregateRoot):
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
        action_deck: ActionDeck,
        action_masteries: Dict[int, ActionMastery] = None,
        race: Race = Race.HUMAN,
        element: Element = Element.NEUTRAL,
    ):
        # プレイヤー固有の属性
        self._player_id = player_id
        self._name = name
        self._role = role
        self._current_spot_id = current_spot_id
        self._previous_spot_id = None
        self._player_state = PlayerState.NORMAL
        self._inventory = inventory
        self._equipment = equipment_set
        self._message_box = message_box
        self._base_status = base_status
        self._dynamic_status = dynamic_status
        self._race = race
        self._element = element
        self._action_deck = action_deck
        self._action_masteries = action_masteries if action_masteries is not None else {}
        # self._appearance = AppearanceSet()  # 将来実装
    
    @property
    def player_id(self) -> int:
        return self._player_id
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def role(self) -> Role:
        return self._role
    
    @property
    def current_spot_id(self) -> int:
        return self._current_spot_id
    
    @property
    def player_state(self) -> PlayerState:
        return self._player_state
    
    @property
    def race(self) -> Race:
        return self._race
    
    @property
    def element(self) -> Element:
        return self._element
    
    @property
    def hp(self) -> Hp:
        return self._dynamic_status.hp
    
    @property
    def mp(self) -> Mp:
        return self._dynamic_status.mp
    
    @property
    def action_deck(self) -> ActionDeck:
        return self._action_deck
    
    @property
    def action_masteries(self) -> Dict[int, ActionMastery]:
        return self._action_masteries.copy()
    
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

    def calculate_status_including_equipment(self) -> BaseStatus:
        """ステータスを計算"""
        return self._base_status + self._equipment.calculate_status()

    # ===== メッセージ関連の振る舞い =====
    def speak(self, content: str, recipient: Optional["Player"] = None):
        if recipient is not None:
            if self._player_id == recipient._player_id:
                raise ValueError("Cannot send message to yourself")
            if self._current_spot_id != recipient._current_spot_id:
                raise ValueError("Cannot send message to a player in a different spot")
            self.add_event(PlayerSpokeEvent(
                aggregate_id=self._player_id,
                aggregate_type="player",
                content=content,
                recipient_id=recipient._player_id,
            ))
        else:
            self.add_event(PlayerSpokeEvent(
                aggregate_id=self._player_id,
                aggregate_type="player",
                content=content,
            ))
    
    def receive_message(self, message: Message):
        """メッセージを受信"""
        self._message_box.append(message)

    def read_messages(self) -> str:
        """メッセージを既読にして表示"""
        messages = self._message_box.read_all()
        if len(messages) == 0:
            return ""
        return "\n".join([message.display() for message in messages])

    # ===== プレイヤーの状態をチェックするメソッド =====
    def level_is_above(self, level: Level) -> bool:
        """プレイヤーのレベルが指定したレベルより上かどうかをチェック"""
        return self._dynamic_status.level >= level

    def has_item(self, item_id: int, quantity: int) -> bool:
        """プレイヤーが指定したアイテムを持っているかどうかをチェック"""
        return self._inventory.has_stackable(item_id, quantity)

    def can_pay_gold(self, gold: Gold) -> bool:
        """プレイヤーが指定した金額を支払えるかどうかをチェック"""
        return self._dynamic_status.can_pay_gold(gold)

    def is_role(self, role: Role) -> bool:
        """プレイヤーの役割が指定した役割かどうかをチェック"""
        return self._role == role

    # ===== 移動関連のメソッド =====
    def move_to_spot(self, to_spot_id: int):
        if self._current_spot_id == to_spot_id:
            raise PlayerAlreadyInSpotException(f"Player {self.player_id} is already in the spot {to_spot_id}")

        self._previous_spot_id = self._current_spot_id
        self._current_spot_id = to_spot_id

        self.add_event(PlayerMovedEvent(
            player_id=self.player_id,
            from_spot_id=self._previous_spot_id,
            to_spot_id=to_spot_id,
        ))
    
    # ===== Actionデッキ関連の振る舞い =====
    def learn_action(self, action_slot: ActionSlot) -> None:
        """技を習得する（ドメインロジック）"""
        # ビジネスルール: 既に習得済みの技は習得できない
        if self._action_deck.has_action(action_slot.action_id):
            raise ValueError(f"Action already learned. action_id: {action_slot.action_id}")
        
        # ビジネスルール: キャパシティ制限
        if not self._action_deck.can_add_action(action_slot):
            raise ValueError(f"Not enough capacity to learn action. action_id: {action_slot.action_id}")
        
        # デッキに技を追加
        self._action_deck = self._action_deck.add_action(action_slot)
        
        # 習熟度を初期化
        if action_slot.action_id not in self._action_masteries:
            self._action_masteries[action_slot.action_id] = ActionMastery(action_slot.action_id, 0, 1)
    
    def forget_action(self, action_id: int, is_basic_action: bool) -> None:
        """技を忘れる（ドメインロジック）"""
        # ビジネスルール: 基本技は忘れることができない
        if is_basic_action:
            raise ValueError(f"Cannot forget basic action. action_id: {action_id}")
        
        # ビジネスルール: 習得していない技は忘れられない
        if not self._action_deck.has_action(action_id):
            raise ValueError(f"Action not learned. action_id: {action_id}")
        
        # デッキから技を削除
        self._action_deck = self._action_deck.remove_action(action_id)
        
        # 習熟度も削除
        if action_id in self._action_masteries:
            del self._action_masteries[action_id]
    
    def evolve_action(self, action_id: int, evolved_action_id: int, evolved_cost: int) -> None:
        """技を進化させる（ドメインロジック）"""
        # ビジネスルール: 習熟度が存在しない技は進化できない
        mastery = self._action_masteries.get(action_id)
        if mastery is None:
            raise ValueError(f"Action mastery not found. action_id: {action_id}")
        
        # ビジネスルール: デッキに存在しない技は進化できない
        current_slot = self._action_deck.get_action_slot(action_id)
        if current_slot is None:
            raise ValueError(f"Action not found in deck. action_id: {action_id}")
        
        # 進化後の技スロットを作成（レベルは引き継ぎ）
        evolved_slot = ActionSlot(evolved_action_id, current_slot.level, evolved_cost)
        
        # キャパシティチェック（一旦削除してから追加）
        temp_deck = self._action_deck.remove_action(action_id)
        if not temp_deck.can_add_action(evolved_slot):
            raise ValueError(f"Not enough capacity for evolved action. evolved_action_id: {evolved_action_id}")
        
        # デッキを更新
        self._action_deck = temp_deck.add_action(evolved_slot)
        
        # 習熟度を更新（進化時はリセット）
        del self._action_masteries[action_id]
        self._action_masteries[evolved_action_id] = ActionMastery(evolved_action_id, 0, 1)
    
    def gain_action_experience(self, action_id: int, experience: int) -> None:
        """技の経験値を獲得"""
        if action_id not in self._action_masteries:
            raise ValueError(f"Action mastery not found. action_id: {action_id}")
        
        current_mastery = self._action_masteries[action_id]
        new_mastery = current_mastery.gain_experience(experience)
        self._action_masteries[action_id] = new_mastery
    
    def level_up_action(self, action_id: int) -> None:
        """技のレベルを上げる"""
        if action_id not in self._action_masteries:
            raise ValueError(f"Action mastery not found. action_id: {action_id}")
        
        current_mastery = self._action_masteries[action_id]
        new_mastery = current_mastery.level_up()
        self._action_masteries[action_id] = new_mastery
        
        # デッキ内のスロットも更新
        current_slot = self._action_deck.get_action_slot(action_id)
        if current_slot is not None:
            new_slot = current_slot.with_level(new_mastery.level)
            self._action_deck = self._action_deck.update_action_slot(action_id, new_slot)
    
    def get_action_mastery(self, action_id: int) -> Optional[ActionMastery]:
        """指定された技の習熟度を取得"""
        return self._action_masteries.get(action_id)
    
    # ===== 戦闘後の状態を適用 =====
    def apply_battle_result(self, combat_state: CombatState):
        """戦闘後の状態を適用"""
        self._dynamic_status.hp = combat_state.current_hp
        self._dynamic_status.mp = combat_state.current_mp