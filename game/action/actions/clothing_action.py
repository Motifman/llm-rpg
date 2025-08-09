from typing import List, Optional

from game.enums import AppearanceSlot
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.item.item import AppearanceItem


class AppearanceCheckResult(ActionResult):
    def __init__(self, success: bool, message: str, appearance_text: str):
        super().__init__(success, message)
        self.appearance_text = appearance_text

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} の見た目を確認しました\n\t{self.appearance_text}"
        else:
            return f"{player_name} の見た目を確認できませんでした\n\t理由:{self.message}"


class EquipClothingResult(ActionResult):
    def __init__(self, success: bool, message: str, item_id: str, previous_item_id: Optional[str], appearance_text: str):
        super().__init__(success, message)
        self.item_id = item_id
        self.previous_item_id = previous_item_id
        self.appearance_text = appearance_text

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            if self.previous_item_id:
                return f"{player_name} は {self.previous_item_id} から {self.item_id} に服飾を変更しました"
            else:
                return f"{player_name} は {self.item_id} を装着しました"
        else:
            return f"{player_name} は {self.item_id} を装着できませんでした\n\t理由:{self.message}"


class UnequipClothingResult(ActionResult):
    def __init__(self, success: bool, message: str, slot_name: str, item_id: Optional[str], appearance_text: str):
        super().__init__(success, message)
        self.slot_name = slot_name
        self.item_id = item_id
        self.appearance_text = appearance_text

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は {self.slot_name} の {self.item_id} を外しました"
        else:
            return f"{player_name} は {self.slot_name} の服飾を外せませんでした\n\t理由:{self.message}"


class AppearanceCheckStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("見た目確認")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext) -> ActionCommand:
        return AppearanceCheckCommand()


class AppearanceCheckCommand(ActionCommand):
    def __init__(self):
        super().__init__("見た目確認")

    def execute(self, acting_player: Player, game_context: GameContext) -> AppearanceCheckResult:
        text = acting_player.get_appearance_text()
        return AppearanceCheckResult(True, "見た目を確認しました", text)


class EquipClothingStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("服飾装着")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        # インベントリ内の服飾アイテムのitem_id候補
        clothing_ids: List[str] = []
        seen = set()
        for item in acting_player.get_inventory().get_items():
            if isinstance(item, AppearanceItem):
                if item.item_id not in seen:
                    seen.add(item.item_id)
                    clothing_ids.append(item.item_id)
        if clothing_ids:
            return [ArgumentInfo(name="item_id", description="装着する服飾アイテムを選択してください", candidates=clothing_ids)]
        return []

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, item_id: str) -> ActionCommand:
        return EquipClothingCommand(item_id)


class EquipClothingCommand(ActionCommand):
    def __init__(self, item_id: str):
        super().__init__("服飾装着")
        self.item_id = item_id

    def execute(self, acting_player: Player, game_context: GameContext) -> EquipClothingResult:
        # 事前にスロットを取得しておく
        item = acting_player.get_inventory().get_item_by_id(self.item_id)
        if item is None or not isinstance(item, AppearanceItem):
            return EquipClothingResult(False, "服飾アイテムが見つかりません", self.item_id, None, acting_player.get_appearance_text())
        slot: AppearanceSlot = item.slot

        previous_item_id = acting_player.equip_clothing(self.item_id)

        # 成否判定: スロットに対象が装着されているか
        equipped = acting_player.appearance.get_equipped(slot)
        success = equipped is not None and equipped.item_id == self.item_id
        if success:
            return EquipClothingResult(True, "服飾を装着しました", self.item_id, previous_item_id, acting_player.get_appearance_text())
        else:
            return EquipClothingResult(False, "服飾を装着できませんでした", self.item_id, previous_item_id, acting_player.get_appearance_text())


class UnequipClothingStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("服飾解除")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        equipped_slots = []
        for slot in AppearanceSlot:
            if acting_player.appearance.get_equipped(slot):
                equipped_slots.append(slot.value)
        if equipped_slots:
            return [ArgumentInfo(name="slot_name", description="外す服飾スロットを選択してください", candidates=equipped_slots)]
        return []

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, slot_name: str) -> ActionCommand:
        try:
            slot = AppearanceSlot(slot_name)
            return UnequipClothingCommand(slot)
        except ValueError:
            return UnequipClothingCommand(None)


class UnequipClothingCommand(ActionCommand):
    def __init__(self, slot: Optional[AppearanceSlot]):
        super().__init__("服飾解除")
        self.slot = slot

    def execute(self, acting_player: Player, game_context: GameContext) -> UnequipClothingResult:
        if self.slot is None:
            return UnequipClothingResult(False, "無効な服飾スロットです", "-", None, acting_player.get_appearance_text())
        removed_id = acting_player.unequip_clothing(self.slot)
        if removed_id:
            return UnequipClothingResult(True, "服飾を外しました", self.slot.value, removed_id, acting_player.get_appearance_text())
        else:
            return UnequipClothingResult(False, "外す服飾がありません", self.slot.value, None, acting_player.get_appearance_text())


