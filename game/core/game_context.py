from game.player.player_manager import PlayerManager
from game.world.spot_manager import SpotManager
from game.sns.sns_manager import SnsManager
from game.conversation.conversation_manager import ConversationManager
from game.trade.trade_manager import TradeManager
from game.quest.quest_manager import QuestSystem
from game.battle.battle_manager import BattleManager


class GameContext:
    def __init__(self, player_manager: PlayerManager, spot_manager: SpotManager, sns_manager: SnsManager = None, conversation_manager: ConversationManager = None, trade_manager: TradeManager = None, quest_system: QuestSystem = None, battle_manager: BattleManager = None):
        self.player_manager = player_manager
        self.spot_manager = spot_manager
        self.sns_manager = sns_manager
        self.conversation_manager = conversation_manager
        self.trade_manager = trade_manager
        self.quest_system = quest_system
        self.battle_manager = battle_manager

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
    
    def get_conversation_manager(self) -> ConversationManager:
        return self.conversation_manager
    
    def get_trade_manager(self) -> TradeManager:
        return self.trade_manager
    
    def get_quest_system(self) -> QuestSystem:
        return self.quest_system
    
    def get_battle_manager(self) -> BattleManager:
        return self.battle_manager


class GameContextBuilder:
    def __init__(self):
        self.player_manager = None
        self.spot_manager = None
        self.sns_manager = None
        self.conversation_manager = None
        self.trade_manager = None
        self.quest_system = None
        self.battle_manager = None
    
    def with_player_manager(self, player_manager: PlayerManager) -> 'GameContextBuilder':
        self.player_manager = player_manager
        return self
    
    def with_spot_manager(self, spot_manager: SpotManager) -> 'GameContextBuilder':
        self.spot_manager = spot_manager
        return self
    
    def with_sns_manager(self, sns_manager: SnsManager) -> 'GameContextBuilder':
        self.sns_manager = sns_manager
        return self
    
    def with_conversation_manager(self, conversation_manager: ConversationManager) -> 'GameContextBuilder':
        self.conversation_manager = conversation_manager
        return self
    
    def with_trade_manager(self, trade_manager: TradeManager) -> 'GameContextBuilder':
        self.trade_manager = trade_manager
        return self
    
    def with_quest_system(self, quest_system: QuestSystem) -> 'GameContextBuilder':
        self.quest_system = quest_system
        return self
    
    def with_battle_manager(self, battle_manager: BattleManager) -> 'GameContextBuilder':
        self.battle_manager = battle_manager
        return self
    
    def build(self) -> GameContext:
        if self.player_manager is None or self.spot_manager is None:
            raise ValueError("player_manager and spot_manager are required")
        return GameContext(self.player_manager, self.spot_manager, self.sns_manager, self.conversation_manager, self.trade_manager, self.quest_system, self.battle_manager)