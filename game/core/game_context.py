from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager


class GameContext:
    def __init__(self):
        self.player_manager = PlayerManager()
        self.spot_manager = SpotManager()

    def get_player_manager(self) -> PlayerManager:
        return self.player_manager
    
    def get_spot_manager(self) -> SpotManager:
        return self.spot_manager