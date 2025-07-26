from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager
from game.sns.sns_manager import SnsManager


class GameContext:
    def __init__(self, player_manager: PlayerManager, spot_manager: SpotManager, sns_manager: SnsManager = None):
        self.player_manager = player_manager
        self.spot_manager = spot_manager
        self.sns_manager = sns_manager

    @classmethod
    def create_basic(cls, player_manager: PlayerManager, spot_manager: SpotManager):
        return cls(player_manager, spot_manager)
    
    @classmethod
    def create_with_sns(cls, player_manager: PlayerManager, spot_manager: SpotManager, sns_manager: SnsManager):
        return cls(player_manager, spot_manager, sns_manager)

    def get_player_manager(self) -> PlayerManager:
        return self.player_manager
    
    def get_spot_manager(self) -> SpotManager:
        return self.spot_manager
    
    def get_sns_manager(self) -> SnsManager:
        return self.sns_manager


class GameContextBuilder:
    def __init__(self):
        self.player_manager = None
        self.spot_manager = None
        self.sns_manager = None
    
    def with_player_manager(self, player_manager: PlayerManager) -> 'GameContextBuilder':
        self.player_manager = player_manager
        return self
    
    def with_spot_manager(self, spot_manager: SpotManager) -> 'GameContextBuilder':
        self.spot_manager = spot_manager
        return self
    
    def with_sns_manager(self, sns_manager: SnsManager) -> 'GameContextBuilder':
        self.sns_manager = sns_manager
        return self
    
    def build(self) -> GameContext:
        if self.player_manager is None or self.spot_manager is None:
            raise ValueError("player_manager and spot_manager are required")
        return GameContext(self.player_manager, self.spot_manager, self.sns_manager)