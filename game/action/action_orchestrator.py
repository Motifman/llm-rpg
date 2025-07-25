from typing import List, Dict, Any
from game.context.game_context import GameContext
from game.action.action_strategy import ActionStrategy
from game.action.actions.move_action import MovementStrategy
from game.action.actions.item_action import UseItemStrategy, PreviewItemEffectStrategy
from game.action.action_result import ActionResult, ErrorActionResult


class ActionOrchestrator:
    def __init__(self, game_context: GameContext):
        self.game_context = game_context
        movement_strategy = MovementStrategy()
        use_item_strategy = UseItemStrategy()
        preview_item_effect_strategy = PreviewItemEffectStrategy()
        self.global_strategies: Dict[str, ActionStrategy] = {
            movement_strategy.get_name(): movement_strategy,
            use_item_strategy.get_name(): use_item_strategy,
            preview_item_effect_strategy.get_name(): preview_item_effect_strategy,
        }

    def get_action_candidates_for_llm(self, acting_player_id: str) -> List[Dict[str, Any]]:
        acting_player = self.game_context.get_player_manager().get_player(acting_player_id)
        if not acting_player: return []

        current_spot = self.game_context.get_player_current_spot(acting_player.player_id)
        if not current_spot: return []

        possible_actions_at_spot = current_spot.get_possible_actions()
        
        candidates = []
        for strategy in possible_actions_at_spot + list(self.global_strategies.values()):
            if strategy.can_execute(acting_player, self.game_context):
                candidates.append({
                    'action_name': strategy.get_name(),
                    'required_arguments_info': strategy.get_required_arguments(acting_player, self.game_context)
                })
        return candidates

    def execute_llm_action(self, acting_player_id: str, action_name: str, action_args: dict) -> ActionResult:
        acting_player = self.game_context.get_player_manager().get_player(acting_player_id)
        if not acting_player:
            return ErrorActionResult(f"プレイヤー {acting_player_id} が見つかりません。")

        strategy = self.global_strategies.get(action_name)
        if not strategy:
            return ErrorActionResult(f"不明な行動名: {action_name}")
        
        if not strategy.can_execute(acting_player, self.game_context):
            return ErrorActionResult(f"{acting_player.name} は {action_name} を実行できません。現在の状態では不可能です。")

        try:
            command = strategy.build_action_command(acting_player, self.game_context, **action_args)
            result = command.execute(acting_player, self.game_context)
            return result
        except ValueError as e:
            return ErrorActionResult(f"行動の引数エラー: {e}")
        except Exception as e:
            return ErrorActionResult(f"行動実行中に予期せぬエラーが発生しました: {e}")