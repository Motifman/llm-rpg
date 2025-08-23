from src.domain.player.player_enum import Role
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.message_box import MessageBox
from src.domain.player.player import Player


class PlayerBuilder:
    def __init__(self, player_id: int, name: str, role: Role, current_spot_id: int):
        self._player_id: int = player_id
        self._name: str = name
        self._role: Role = role
        self._current_spot_id: int = current_spot_id
    
    def with_base_status(self, base_status: BaseStatus) -> "PlayerBuilder":
        self._base_status = base_status
        return self
    
    def with_dynamic_status(self, dynamic_status: DynamicStatus) -> "PlayerBuilder":
        self._dynamic_status = dynamic_status
        return self
    
    def with_inventory(self, inventory: Inventory) -> "PlayerBuilder":
        self._inventory = inventory
        return self
    
    def with_equipment_set(self, equipment_set: EquipmentSet) -> "PlayerBuilder":
        self._equipment_set = equipment_set
        return self
    
    def with_message_box(self, message_box: MessageBox) -> "PlayerBuilder":
        self._message_box = message_box
        return self
    
    def build(self) -> Player:
        return Player(
            player_id=self._player_id,
            name=self._name,
            role=self._role,
            current_spot_id=self._current_spot_id,
            base_status=self._base_status,
            dynamic_status=self._dynamic_status,
            inventory=self._inventory,
            equipment_set=self._equipment_set,
            message_box=self._message_box
        )