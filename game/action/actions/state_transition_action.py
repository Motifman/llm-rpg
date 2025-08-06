from typing import List
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.enums import PlayerState


# ===== 取引所関連の状態遷移 =====

class TradingOpenResult(ActionResult):
    """取引所を開く結果"""
    def __init__(self, success: bool, message: str):
        super().__init__(success, message)
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は取引所を開きました"
        else:
            return f"{player_name} は取引所を開けませんでした\n\t理由:{self.message}"


class TradingCloseResult(ActionResult):
    """取引所を閉じる結果"""
    def __init__(self, success: bool, message: str):
        super().__init__(success, message)
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は取引所を閉じました"
        else:
            return f"{player_name} は取引所を閉じることができませんでした\n\t理由:{self.message}"


class TradingOpenCommand(ActionCommand):
    """取引所を開くコマンド"""
    
    def __init__(self):
        pass

    def execute(self, acting_player: Player, game_context: GameContext) -> TradingOpenResult:
        # プレイヤーの状態を取引に変更
        acting_player.set_player_state(PlayerState.TRADING)
        return TradingOpenResult(True, "取引所を開きました")


class TradingCloseCommand(ActionCommand):
    """取引所を閉じるコマンド"""
    
    def __init__(self):
        pass

    def execute(self, acting_player: Player, game_context: GameContext) -> TradingCloseResult:
        # プレイヤーの状態を通常に変更
        acting_player.set_player_state(PlayerState.NORMAL)
        return TradingCloseResult(True, "取引所を閉じました")


class TradingOpenStrategy(ActionStrategy):
    """取引所を開く戦略"""
    
    def __init__(self):
        super().__init__("取引所を開く")
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # 通常状態の時のみ取引所を開ける
        return acting_player.is_in_normal_state()
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> TradingOpenCommand:
        return TradingOpenCommand()


class TradingCloseStrategy(ActionStrategy):
    """取引所を閉じる戦略"""
    
    def __init__(self):
        super().__init__("取引所を閉じる")
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # 取引状態の時のみ取引所を閉じられる
        return acting_player.is_in_trading_state()
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> TradingCloseCommand:
        return TradingCloseCommand()


# ===== 会話離脱関連の状態遷移 =====

class ConversationLeaveResult(ActionResult):
    """会話を離脱する結果"""
    def __init__(self, success: bool, message: str):
        super().__init__(success, message)
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は会話から離脱しました"
        else:
            return f"{player_name} は会話から離脱できませんでした\n\t理由:{self.message}"


class ConversationLeaveCommand(ActionCommand):
    """会話を離脱するコマンド"""
    
    def __init__(self):
        pass

    def execute(self, acting_player: Player, game_context: GameContext) -> ConversationLeaveResult:
        # プレイヤーの状態を通常に変更
        acting_player.set_player_state(PlayerState.NORMAL)
        return ConversationLeaveResult(True, "会話から離脱しました")


class ConversationLeaveStrategy(ActionStrategy):
    """会話を離脱する戦略"""
    
    def __init__(self):
        super().__init__("会話を離脱する")
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # 会話状態の時のみ会話を離脱できる
        return acting_player.is_in_conversation_state()
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> ConversationLeaveCommand:
        return ConversationLeaveCommand()