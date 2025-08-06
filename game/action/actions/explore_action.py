from typing import List, Optional
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.world.poi_progress import POIExplorationResult
from game.enums import PlayerState


class ExploreActionResult(ActionResult):
    def __init__(
        self,
        success: bool,
        message: str,
        exploration_summary: str,
        poi_result: Optional[POIExplorationResult] = None
    ):
        super().__init__(success, message)
        self.exploration_summary = exploration_summary
        self.poi_result = poi_result

    def to_feedback_message(self, player_name: str) -> str:
        if not self.success:
            return f"{player_name} は探索に失敗しました\n\t理由:{self.message}"

        message = f"{player_name} は周囲を探索しました\n\t探索結果:\n{self.exploration_summary}"
        
        if self.poi_result:
            message += "\n特別な発見:"
            message += f"\n{self.poi_result.description}"
            
            if self.poi_result.found_items:
                message += "\n\t発見したアイテム:"
                for item_id in self.poi_result.found_items:
                    message += f"\n\t- {item_id}"
                    
            if self.poi_result.unlocked_pois:
                message += "\n\t新たに調査可能になった場所:"
                for poi_id in self.poi_result.unlocked_pois:
                    message += f"\n\t- {poi_id}"
        
        return message


class ExploreActionStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("探索")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        current_spot = game_context.get_spot_manager().get_spot(acting_player.get_current_spot_id())
        poi_manager = game_context.get_poi_manager()
        available_pois = poi_manager.get_available_pois(current_spot.spot_id, acting_player)
        
        if not available_pois:
            return []  # 調査可能なPOIがない場合は引数不要
            
        return [
            ArgumentInfo(
                name="poi_id",
                description="調査する場所のID",
                candidates=[poi.poi_id for poi in available_pois]
            )
        ]
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, poi_id: Optional[str] = None) -> ActionCommand:
        return ExploreActionCommand(poi_id)


class ExploreActionCommand(ActionCommand):
    def __init__(self, poi_id: Optional[str] = None):
        super().__init__("探索")
        self.poi_id = poi_id

    def execute(self, acting_player: Player, game_context: GameContext) -> ExploreActionResult:
        current_spot_id = acting_player.get_current_spot_id()
        current_spot = game_context.get_spot_manager().get_spot(current_spot_id)
        
        # 基本的な探索サマリーを取得
        exploration_summary = current_spot.get_exploration_summary(acting_player, game_context)
        
        # POIの探索
        poi_result = None
        if self.poi_id:
            poi_manager = game_context.get_poi_manager()
            try:
                poi_result = poi_manager.explore_poi(
                    current_spot_id,
                    self.poi_id,
                    acting_player,
                    game_context
                )
                if poi_result.encountered_monsters:
                    acting_player.set_player_state(PlayerState.BATTLE)
            except ValueError as e:
                return ExploreActionResult(False, str(e), "", None)
                
        return ExploreActionResult(True, "探索しました", exploration_summary, poi_result)