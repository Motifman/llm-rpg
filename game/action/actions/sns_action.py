from typing import List
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.sns.sns_data import SnsUser


class SnsGetUserInfoResult(ActionResult):
    def __init__(self, success: bool, message: str, user_info: SnsUser):
        super().__init__(success, message)
        self.user_info = user_info
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は {self.user_info.name} の情報を取得しました\n\t{repr(self.user_info)}"
        else:
            return f"{player_name} は {self.user_info.name} の情報を取得できませんでした\n\t理由:{self.message}"


class SnsGetUserInfoStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("SNSユーザー情報取得")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        # SNSユーザーIDを自由入力として要求
        return [ArgumentInfo(
            name="user_id",
            description="情報を取得するSNSユーザーIDを入力してください",
            candidates=None  # 自由入力
        )]
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, user_id: str) -> ActionCommand:
        return SnsGetUserInfoCommand(user_id)


class SnsGetUserInfoCommand(ActionCommand):
    def __init__(self, user_id: str):
        super().__init__("SNSユーザー情報取得")
        self.user_id = user_id

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsGetUserInfoResult:
        sns_manager = game_context.get_sns_manager()
        user_info = sns_manager.get_user(self.user_id)
        if user_info is None:
            return SnsGetUserInfoResult(False, f"ユーザー {self.user_id} が存在しません", None)
        return SnsGetUserInfoResult(True, f"ユーザー {self.user_id} の情報を取得しました", user_info)