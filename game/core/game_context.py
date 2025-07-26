from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager


class GameContext:
    def __init__(self, player_manager: PlayerManager, spot_manager: SpotManager):
        self.player_manager = player_manager
        self.spot_manager = spot_manager

    def get_player_manager(self) -> PlayerManager:
        return self.player_manager
    
    def get_spot_manager(self) -> SpotManager:
        return self.spot_manager