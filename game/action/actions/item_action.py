from typing import List, Optional
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.item.item_effect import ItemEffect


class ItemUseResult(ActionResult):
    def __init__(self, success: bool, message: str, item_id: str, 
                 effect: Optional[ItemEffect] = None, 
                 status_before: Optional[dict] = None,
                 status_after: Optional[dict] = None):
        super().__init__(success, message)
        self.item_id = item_id
        self.effect = effect
        self.status_before = status_before
        self.status_after = status_after
    
    def get_effect_description(self) -> str:
        if not self.effect:
            return "効果なし"
        return str(self.effect)
    
    def get_status_change_description(self) -> str:
        if not self.status_before or not self.status_after:
            return ""
        
        changes = []
        if self.status_after['hp'] != self.status_before['hp']:
            change = self.status_after['hp'] - self.status_before['hp']
            changes.append(f"HP: {self.status_before['hp']} → {self.status_after['hp']} ({change:+d})")
        
        if self.status_after['mp'] != self.status_before['mp']:
            change = self.status_after['mp'] - self.status_before['mp']
            changes.append(f"MP: {self.status_before['mp']} → {self.status_after['mp']} ({change:+d})")
        
        if self.status_after['attack'] != self.status_before['attack']:
            change = self.status_after['attack'] - self.status_before['attack']
            changes.append(f"攻撃力: {self.status_before['attack']} → {self.status_after['attack']} ({change:+d})")
        
        if self.status_after['defense'] != self.status_before['defense']:
            change = self.status_after['defense'] - self.status_before['defense']
            changes.append(f"防御力: {self.status_before['defense']} → {self.status_after['defense']} ({change:+d})")
        
        if self.status_after['gold'] != self.status_before['gold']:
            change = self.status_after['gold'] - self.status_before['gold']
            changes.append(f"所持金: {self.status_before['gold']} → {self.status_after['gold']} ({change:+d})")
        
        if self.status_after['experience_points'] != self.status_before['experience_points']:
            change = self.status_after['experience_points'] - self.status_before['experience_points']
            changes.append(f"経験値: {self.status_before['experience_points']} → {self.status_after['experience_points']} ({change:+d})")
        
        new_effects = []
        for effect in self.effect.temporary_effects:
            new_effects.append(f"{effect.effect.value}: {effect.duration}ターン")
        
        if new_effects:
            changes.append(f"一時効果: {', '.join(new_effects)}")
        
        return "\n".join(changes) if changes else "変化なし"
    
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は {self.item_id} を使用しました\n{self.get_effect_description()}\n{self.get_status_change_description()}"
        else:
            return f"{player_name} は {self.item_id} を使用できませんでした\n\t理由:{self.message}"


class PreviewItemEffectResult(ActionResult):
    def __init__(self, success: bool, message: str, item_id: str, effect_description: str = ""):
        super().__init__(success, message)
        self.item_id = item_id
        self.effect_description = effect_description

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は {self.item_id} の効果を確認しました\n{self.effect_description}"
        else:
            return f"{player_name} は {self.item_id} の効果を確認できませんでした\n\t理由:{self.message}"


class UseItemStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("消費アイテムの使用")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        consumable_item_ids = acting_player.get_all_consumable_item_ids()
        
        if consumable_item_ids:
            return [ArgumentInfo(
                name="item_id",
                description="使用する消費アイテムを選択してください",
                candidates=consumable_item_ids
            )]
        else:
            return []
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return len(self.get_required_arguments(acting_player, game_context)) > 0

    def build_action_command(self, acting_player: Player, game_context: GameContext, item_id: str) -> ActionCommand:
        return UseItemCommand(item_id)


class UseItemCommand(ActionCommand):
    def __init__(self, item_id: str):
        super().__init__("消費アイテムの使用")
        self.item_id = item_id

    def execute(self, acting_player: Player, game_context: GameContext) -> ItemUseResult:
        item_use_result = acting_player.use_item(self.item_id)
        return item_use_result


class PreviewItemEffectStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("アイテム効果の確認")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        consumable_item_ids = acting_player.get_all_consumable_item_ids()
        
        if consumable_item_ids:
            return [ArgumentInfo(
                name="item_id",
                description="効果を確認する消費アイテムを選択してください",
                candidates=consumable_item_ids
            )]
        else:
            return []
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return len(self.get_required_arguments(acting_player, game_context)) > 0

    def build_action_command(self, acting_player: Player, game_context: GameContext, item_id: str) -> ActionCommand:
        return PreviewItemEffectCommand(item_id)


class PreviewItemEffectCommand(ActionCommand):
    def __init__(self, item_id: str):
        super().__init__("アイテム効果の確認")
        self.item_id = item_id

    def execute(self, acting_player: Player, game_context: GameContext) -> PreviewItemEffectResult:
        effect = acting_player.preview_item_effect(self.item_id)
        if effect is None:
            return PreviewItemEffectResult(
                success=False,
                message="アイテムが見つからないか、消費アイテムではありません",
                item_id=self.item_id
            )
        
        return PreviewItemEffectResult(
            success=True,
            message="アイテム効果を確認しました",
            item_id=self.item_id,
            effect_description=str(effect)
        )