from typing import List, Optional
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.sns.sns_data import SnsUser, Post
from game.enums import PostVisibility


class SnsGetUserInfoResult(ActionResult):
    def __init__(self, success: bool, message: str, user_info: SnsUser):
        super().__init__(success, message)
        self.user_info = user_info
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は {self.user_info.name} の情報を取得しました\n\t{repr(self.user_info)}"
        else:
            return f"{player_name} は {self.user_info.name} の情報を取得できませんでした\n\t理由:{self.message}"


class SnsUpdateUserBioResult(ActionResult):
    def __init__(self, success: bool, message: str):
        super().__init__(success, message)
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} はユーザー情報を更新しました"
        else:
            return f"{player_name} はユーザー情報を更新できませんでした\n\t理由:{self.message}"


class SnsPostResult(ActionResult):
    def __init__(self, success: bool, message: str, post_id: str):
        super().__init__(success, message)
        self.post_id = post_id

    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は投稿を作成しました\n\t{self.post_id}"
        else:
            return f"{player_name} は投稿を作成できませんでした\n\t理由:{self.message}"


class SnsGetTimelineResult(ActionResult):
    def __init__(self, success: bool, message: str, posts: List[Post]):
        super().__init__(success, message)
        self.posts = posts
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} はタイムラインを取得しました\n\t{self.posts}"
        else:
            return f"{player_name} はタイムラインを取得できませんでした\n\t理由:{self.message}"


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


class SnsUpdateUserBioStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("SNSユーザー情報更新")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [ArgumentInfo(
            name="bio",
            description="更新するユーザーの一言コメントを入力してください",
            candidates=None  # 自由入力
        )]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, bio: str) -> ActionCommand:
        return SnsUpdateUserBioCommand(bio)


class SnsPostStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("SNS投稿")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="content",
                description="投稿内容を入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="hashtags",
                description="投稿に含めるハッシュタグを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="visibility",
                description="投稿の可視性を選択してください",
                candidates=PostVisibility.values()
            ),
            ArgumentInfo(
                name="allowed_users",
                description="閲覧を許可するユーザーIDを入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, content: str) -> ActionCommand:
        return SnsPostCommand(content)


class SnsGetTimelineStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("SNSタイムライン取得")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="timeline_type",
                description="タイムラインの種類を選択してください",
                candidates=["global", "personalized", "following", "hashtag"]
            ),
            ArgumentInfo(
                name="hashtag",
                description="タイムラインを取得するハッシュタグを入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, timeline_type: str, hashtag: str) -> ActionCommand:
        return SnsGetTimelineCommand(timeline_type, hashtag)


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


class SnsUpdateUserBioCommand(ActionCommand):
    def __init__(self, bio: str):
        super().__init__("SNSユーザー情報更新")
        self.bio = bio

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsUpdateUserBioResult:
        sns_manager = game_context.get_sns_manager()
        sns_manager.update_user_bio(acting_player.get_id(), self.bio)
        return SnsUpdateUserBioResult(True, "ユーザー情報を更新しました")


class SnsPostCommand(ActionCommand):
    def __init__(self, content: str, hashtags: List[str], visibility: PostVisibility, allowed_users: List[str]):
        super().__init__("SNS投稿")
        self.content = content
        self.hashtags = hashtags
        self.visibility = visibility
        self.allowed_users = allowed_users

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsPostResult:
        sns_manager = game_context.get_sns_manager()
        post_id = sns_manager.create_post(acting_player.get_id(), self.content, self.hashtags, self.visibility, self.allowed_users)
        return SnsPostResult(True, "投稿を作成しました", post_id)


class SnsGetTimelineCommand(ActionCommand):
    def __init__(self, timeline_type: str, hashtag: Optional[str] = None):
        super().__init__("SNSタイムライン取得")
        self.timeline_type = timeline_type
        self.hashtag = hashtag

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsGetTimelineResult:
        player_id = acting_player.get_player_id()
        sns_manager = game_context.get_sns_manager()
        try:
            if self.timeline_type == "global":
                posts = sns_manager.get_global_timeline(limit=10)
            elif self.timeline_type == "personalized":
                posts = sns_manager.get_global_timeline(player_id, limit=10)
            elif self.timeline_type == "following":
                posts = sns_manager.get_following_timeline(player_id, limit=10)
            elif self.timeline_type == "hashtag":
                posts = sns_manager.get_hashtag_timeline(self.hashtag, player_id, limit=10)
            return SnsGetTimelineResult(True, "タイムラインを取得しました", posts)
        except Exception as e:
            return SnsGetTimelineResult(False, f"タイムラインを取得できませんでした: {e}", [])