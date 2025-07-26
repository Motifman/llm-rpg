from typing import List, Dict, TYPE_CHECKING
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy
from game.player.player import Player
from game.core.game_context import GameContext

# 型ヒントの遅延インポート
if TYPE_CHECKING:
    from game.object.chest import Chest


class OpenChestResult(ActionResult):
    def __init__(self, success: bool, message: str, items_details: List[str] = None):
        super().__init__(success, message)
        self.items_details = items_details
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            items_text = '\n\t'.join(self.items_details) if self.items_details else "なし"
            return f"{player_name} は宝箱を開けてアイテムを入手しました\n\t入手したアイテム:\n\t{items_text}"
        else:
            return f"{player_name} は宝箱を開けることに失敗しました\n\t理由:{self.message}"


class OpenChestStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("宝箱を開ける")
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[str]:
        """利用可能なチェストの表示名を返す"""
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return []
        
        available_chests = []
        for interactable in current_spot.get_all_interactables():
            from game.object.chest import Chest
            if isinstance(interactable, Chest) and not interactable.is_opened:
                available_chests.append(interactable.get_display_name())
        
        return available_chests
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        if not current_spot:
            return False
        
        for interactable in current_spot.get_all_interactables():
            from game.object.chest import Chest
            if isinstance(interactable, Chest) and not interactable.is_opened:
                return True
        return False
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> ActionCommand:
        target_chest_name = kwargs.get('chest_name', None)
        return OpenChestCommand(target_chest_name)


class OpenChestCommand(ActionCommand):
    def __init__(self, target_chest_name: str = None):
        super().__init__("宝箱を開ける")
        self.target_chest_name = target_chest_name
    
    def execute(self, acting_player: Player, game_context: GameContext) -> OpenChestResult:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)

        if not current_spot:
            return OpenChestResult(
                success=False,
                message="現在のスポットが見つかりません"
            )
        
        available_chests = []
        for interactable in current_spot.get_all_interactables():
            from game.object.chest import Chest
            if isinstance(interactable, Chest) and not interactable.is_opened:
                available_chests.append(interactable)
        
        if not available_chests:
            return OpenChestResult(
                success=False,
                message="この場所に開けることができる宝箱はありません",
                items_details=[]
            )
        
        target_chest = None
        if self.target_chest_name:
            for chest in available_chests:
                if chest.get_display_name() == self.target_chest_name:
                    target_chest = chest
                    break
            
            if not target_chest:
                available_names = [chest.get_display_name() for chest in available_chests]
                return OpenChestResult(
                    success=False,
                    message=f"「{self.target_chest_name}」という名前の宝箱は見つかりません。利用可能な宝箱: {', '.join(available_names)}",
                    items_details=[]
                )
        else:
            target_chest = available_chests[0]
        
        if target_chest.is_locked:
            if not target_chest.required_item_id:
                return OpenChestResult(
                    success=False,
                    message="宝箱は鍵でロックされています",
                    items_details=[]
                )
            
            if not acting_player.has_item(target_chest.required_item_id):
                return OpenChestResult(
                    success=False,
                    message=f"宝箱を開けるには「{target_chest.required_item_id}」が必要です",
                    items_details=[]
                )
            
            target_chest.unlock()
            acting_player.remove_item(target_chest.required_item_id)
        
        items = target_chest.open()
        for item in items:
            acting_player.add_item(item)
        
        if items:
            item_details = [str(item) for item in items]
            message = f"「{target_chest.get_display_name()}」を開けてアイテムを入手しました"
        else:
            message = f"「{target_chest.get_display_name()}」を開けましたが、中は空でした"
            item_details = []
        
        return OpenChestResult(
            success=True,
            message=message,
            items_details=item_details
        )