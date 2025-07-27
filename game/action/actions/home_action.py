from typing import List
from game.action.actions.permission_checked_action import PermissionCheckedActionStrategy
from game.action.action_strategy import ArgumentInfo
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.player.player import Player
from game.core.game_context import GameContext
from game.enums import Permission


class SleepActionStrategy(PermissionCheckedActionStrategy):
    """睡眠アクション（OWNER権限が必要）"""
    
    def __init__(self):
        super().__init__("睡眠", Permission.OWNER)
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []  # 引数不要
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> ActionCommand:
        return SleepActionCommand()


class SleepActionCommand(ActionCommand):
    """睡眠コマンド"""
    
    def __init__(self):
        super().__init__("睡眠")
    
    def execute(self, acting_player: Player, game_context: GameContext) -> ActionResult:
        # 睡眠の効果を実装
        health_restored = 50
        mana_restored = 30
        
        acting_player.restore_health(health_restored)
        acting_player.restore_mana(mana_restored)
        
        return SleepActionResult(
            success=True,
            message=f"{acting_player.name}はベッドで眠り、体力を回復しました。",
            health_restored=health_restored,
            mana_restored=mana_restored
        )


class SleepActionResult(ActionResult):
    """睡眠アクションの結果"""
    
    def __init__(self, success: bool, message: str, health_restored: int, mana_restored: int):
        super().__init__(success, message)
        self.health_restored = health_restored
        self.mana_restored = mana_restored
        self.data = {
            "health_restored": health_restored,
            "mana_restored": mana_restored
        }
    
    def to_feedback_message(self, player_name: str) -> str:
        return f"{player_name}はベッドで眠り、体力を{self.health_restored}、マナを{self.mana_restored}回復しました。"


class WriteDiaryActionStrategy(PermissionCheckedActionStrategy):
    """日記を書くアクション（OWNER権限が必要）"""
    
    def __init__(self):
        super().__init__("日記を書く", Permission.OWNER)
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="content",
                description="日記の内容",
                candidates=None
            )
        ]
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> ActionCommand:
        content = kwargs.get("content", "")
        return WriteDiaryActionCommand(content)


class WriteDiaryActionCommand(ActionCommand):
    """日記を書くコマンド"""
    
    def __init__(self, content: str):
        super().__init__("日記を書く")
        self.content = content
    
    def execute(self, acting_player: Player, game_context: GameContext) -> ActionResult:
        # 日記を書く効果を実装
        exp_gained = 10
        
        acting_player.gain_experience(exp_gained)
        
        return WriteDiaryActionResult(
            success=True,
            message=f"{acting_player.name}は日記を書きました。",
            content=self.content,
            exp_gained=exp_gained
        )


class WriteDiaryActionResult(ActionResult):
    """日記を書くアクションの結果"""
    
    def __init__(self, success: bool, message: str, content: str, exp_gained: int):
        super().__init__(success, message)
        self.content = content
        self.exp_gained = exp_gained
        self.data = {
            "content": content,
            "exp_gained": exp_gained
        }
    
    def to_feedback_message(self, player_name: str) -> str:
        return f"{player_name}は日記を書きました。経験値を{self.exp_gained}獲得しました。" 