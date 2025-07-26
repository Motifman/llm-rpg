from typing import List, Optional
from game.enums import EquipmentSlot
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext


class EquipmentSetCheckResult(ActionResult):
    def __init__(self, success: bool, message: str, equipment_summary: str):
        super().__init__(success, message)
        self.equipment_summary = equipment_summary

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} の装備を確認しました\n\t装備:{self.equipment_summary}"
        else:
            return f"{player_name} の装備を確認できませんでした\n\t理由:{self.message}"


class EquipItemResult(ActionResult):
    def __init__(self, success: bool, message: str, equipment_summary: str, equipment_name: str, old_equipment_name: Optional[str] = None):
        super().__init__(success, message)
        self.equipment_name = equipment_name
        self.old_equipment_name = old_equipment_name
        self.equipment_summary = equipment_summary

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            if self.old_equipment_name:
                return f"{player_name} は {self.old_equipment_name} から {self.equipment_name} に装備を変更しました\n\t現在の装備:{self.equipment_summary}"
            else:
                return f"{player_name} は {self.equipment_name} を装備しました\n\t現在の装備:{self.equipment_summary}"
        else:
            if self.old_equipment_name:
                return f"{player_name} は {self.old_equipment_name} から {self.equipment_name} に装備を変更できませんでした\n\t理由:{self.message}"
            else:
                return f"{player_name} は {self.equipment_name} を装備できませんでした\n\t理由:{self.message}"


class UnequipItemResult(ActionResult):
    def __init__(self, success: bool, message: str, equipment_summary: str, equipment_name: str):
        super().__init__(success, message)
        self.equipment_name = equipment_name
        self.equipment_summary = equipment_summary

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は {self.equipment_name} を装備を外しました\n\t現在の装備:{self.equipment_summary}"
        else:
            return f"{player_name} は {self.equipment_name} を装備を外せませんでした\n\t理由:{self.message}"


class EquipmentSetCheckStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("装備確認")
        
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []  # 引数不要
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return EquipmentSetCheckCommand()


class EquipItemStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("装備変更")
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        equipment_item_ids = acting_player.get_all_equipment_item_ids()
        
        if equipment_item_ids:
            return [ArgumentInfo(
                name="item_id",
                description="装備するアイテムを選択してください",
                candidates=equipment_item_ids
            )]
        else:
            return []
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, item_id: str) -> ActionCommand:
        return EquipItemCommand(item_id)


class UnequipItemStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("装備解除")
        
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        equipped_slots = acting_player.get_equipped_slots()
        slot_names = [slot.value for slot in equipped_slots]
        
        if slot_names:
            return [ArgumentInfo(
                name="slot_name",
                description="装備を外すスロットを選択してください",
                candidates=slot_names
            )]
        else:
            return []
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, slot_name: str) -> ActionCommand:
        try:
            slot = EquipmentSlot(slot_name)
            return UnequipItemCommand(slot)
        except ValueError:
            return UnequipItemCommand(None)


class EquipmentSetCheckCommand(ActionCommand):
    def __init__(self):
        super().__init__("装備確認")

    def execute(self, acting_player: Player, game_context: GameContext) -> EquipmentSetCheckResult:
        equipment = acting_player.get_equipment()
        equipment_summary = str(equipment)
        return EquipmentSetCheckResult(True, "装備を確認しました", equipment_summary)


class EquipItemCommand(ActionCommand):
    def __init__(self, item_id: str):
        super().__init__("装備変更")
        self.item_id = item_id

    def execute(self, acting_player: Player, game_context: GameContext) -> EquipItemResult:
        return acting_player.equip_item(self.item_id)


class UnequipItemCommand(ActionCommand):
    def __init__(self, slot: Optional[EquipmentSlot] = None):
        super().__init__("装備解除")
        self.slot = slot

    def execute(self, acting_player: Player, game_context: GameContext) -> UnequipItemResult:
        if self.slot is None:
            return UnequipItemResult(False, "無効な装備スロットです", str(acting_player.get_equipment()), None)
        
        return acting_player.unequip_slot(self.slot)