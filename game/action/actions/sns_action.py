from typing import List, Optional
from game.action.action_command import ActionCommand
from game.action.action_result import ActionResult
from game.action.action_strategy import ActionStrategy, ArgumentInfo
from game.player.player import Player
from game.core.game_context import GameContext
from game.sns.sns_data import SnsUser, Post, Reply, Notification
from game.enums import PostVisibility, NotificationType, PlayerState


class SnsGetUserInfoResult(ActionResult):
    def __init__(self, success: bool, message: str, user_info: SnsUser):
        super().__init__(success, message)
        self.user_info = user_info
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            user_display = self.user_info.format_for_display()
            return f"{player_name} はユーザー情報を取得しました\n\t{user_display}"
        else:
            return f"{player_name} はユーザー情報を取得できませんでした\n\t理由:{self.message}"


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
    def __init__(self, success: bool, message: str, posts: List[str]):
        super().__init__(success, message)
        self.posts = posts
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            posts_text = '\n'.join(self.posts)
            return f"{player_name} はタイムラインを取得しました\n\t{posts_text}"
        else:
            return f"{player_name} はタイムラインを取得できませんでした\n\t理由:{self.message}"


class SnsLikeResult(ActionResult):
    def __init__(self, success: bool, message: str, post_id: str):
        super().__init__(success, message)
        self.post_id = post_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は投稿にいいねしました\n\t投稿ID: {self.post_id}"
        else:
            return f"{player_name} は投稿にいいねできませんでした\n\t理由:{self.message}"


class SnsUnlikeResult(ActionResult):
    def __init__(self, success: bool, message: str, post_id: str):
        super().__init__(success, message)
        self.post_id = post_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は投稿のいいねを解除しました\n\t投稿ID: {self.post_id}"
        else:
            return f"{player_name} は投稿のいいねを解除できませんでした\n\t理由:{self.message}"


class SnsReplyResult(ActionResult):
    def __init__(self, success: bool, message: str, post_id: str, reply_id: str):
        super().__init__(success, message)
        self.post_id = post_id
        self.reply_id = reply_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は投稿に返信しました\n\t投稿ID: {self.post_id}\n\t返信ID: {self.reply_id}"
        else:
            return f"{player_name} は投稿に返信できませんでした\n\t理由:{self.message}"


class SnsGetNotificationsResult(ActionResult):
    def __init__(self, success: bool, message: str, notifications: List[str]):
        super().__init__(success, message)
        self.notifications = notifications
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            notifications_text = '\n'.join(self.notifications)
            return f"{player_name} は通知を取得しました\n\t{notifications_text}"
        else:
            return f"{player_name} は通知を取得できませんでした\n\t理由:{self.message}"


class SnsMarkNotificationReadResult(ActionResult):
    def __init__(self, success: bool, message: str, notification_id: str):
        super().__init__(success, message)
        self.notification_id = notification_id
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} は通知を既読にしました\n\t通知ID: {self.notification_id}"
        else:
            return f"{player_name} は通知を既読にできませんでした\n\t理由:{self.message}"


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
                description="投稿内容を入力してください(100文字以内, ハッシュタグや@をつけてメンションも可能)",
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
                candidates=[v.value for v in PostVisibility]
            ),
            ArgumentInfo(
                name="allowed_users",
                description="閲覧を許可するユーザーIDを入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, content: str, hashtags: List[str] = None, visibility: str = "public", allowed_users: List[str] = None) -> ActionCommand:
        if hashtags is None:
            hashtags = []
        if allowed_users is None:
            allowed_users = []
        
        # 文字列をPostVisibilityに変換
        try:
            visibility_enum = PostVisibility(visibility)
        except ValueError:
            visibility_enum = PostVisibility.PUBLIC
        
        return SnsPostCommand(content, hashtags, visibility_enum, allowed_users)


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


class SnsLikeStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("SNS投稿にいいね")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="post_id",
                description="いいねする投稿のIDを入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, post_id: str) -> ActionCommand:
        return SnsLikeCommand(post_id)


class SnsUnlikeStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("SNS投稿のいいね解除")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="post_id",
                description="いいねを解除する投稿のIDを入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, post_id: str) -> ActionCommand:
        return SnsUnlikeCommand(post_id)


class SnsReplyStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("SNS投稿に返信")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="post_id",
                description="返信する投稿のIDを入力してください",
                candidates=None  # 自由入力
            ),
            ArgumentInfo(
                name="content",
                description="返信内容を入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, post_id: str, content: str) -> ActionCommand:
        return SnsReplyCommand(post_id, content)


class SnsGetNotificationsStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("SNS通知取得")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="unread_only",
                description="未読通知のみを取得するかどうか",
                candidates=["true", "false"]
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, unread_only: str) -> ActionCommand:
        return SnsGetNotificationsCommand(unread_only.lower() == "true")


class SnsMarkNotificationReadStrategy(ActionStrategy):
    def __init__(self):
        super().__init__("SNS通知を既読にする")

    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return [
            ArgumentInfo(
                name="notification_id",
                description="既読にする通知のIDを入力してください",
                candidates=None  # 自由入力
            )
        ]

    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        return True

    def build_action_command(self, acting_player: Player, game_context: GameContext, notification_id: str) -> ActionCommand:
        return SnsMarkNotificationReadCommand(notification_id)


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
        sns_manager.update_user_bio(acting_player.get_player_id(), self.bio)
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
        post = sns_manager.create_post(acting_player.get_player_id(), self.content, self.hashtags, self.visibility, self.allowed_users)
        if post:
            return SnsPostResult(True, "投稿を作成しました", post.post_id)
        else:
            return SnsPostResult(False, "投稿の作成に失敗しました", "")


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
            posts = [post.format_for_timeline() for post in posts]
            return SnsGetTimelineResult(True, "タイムラインを取得しました", posts)
        except Exception as e:
            return SnsGetTimelineResult(False, f"タイムラインを取得できませんでした: {e}", [])


class SnsLikeCommand(ActionCommand):
    def __init__(self, post_id: str):
        super().__init__("SNS投稿にいいね")
        self.post_id = post_id

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsLikeResult:
        player_id = acting_player.get_player_id()
        sns_manager = game_context.get_sns_manager()
        
        try:
            # 投稿が存在するかチェック
            post = sns_manager.get_post(self.post_id)
            if post is None:
                return SnsLikeResult(False, f"投稿ID {self.post_id} が見つかりません", self.post_id)
            
            # 既にいいね済みかチェック
            if sns_manager.has_liked(player_id, self.post_id):
                return SnsLikeResult(False, "既にいいね済みです", self.post_id)
            
            # いいねを実行
            success = sns_manager.like_post(player_id, self.post_id)
            if success:
                return SnsLikeResult(True, "投稿にいいねしました", self.post_id)
            else:
                return SnsLikeResult(False, "いいねに失敗しました", self.post_id)
        except Exception as e:
            return SnsLikeResult(False, f"いいね中にエラーが発生しました: {e}", self.post_id)


class SnsUnlikeCommand(ActionCommand):
    def __init__(self, post_id: str):
        super().__init__("SNS投稿のいいね解除")
        self.post_id = post_id

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsUnlikeResult:
        player_id = acting_player.get_player_id()
        sns_manager = game_context.get_sns_manager()
        
        try:
            # 投稿が存在するかチェック
            post = sns_manager.get_post(self.post_id)
            if post is None:
                return SnsUnlikeResult(False, f"投稿ID {self.post_id} が見つかりません", self.post_id)
            
            # いいね済みかチェック
            if not sns_manager.has_liked(player_id, self.post_id):
                return SnsUnlikeResult(False, "まだいいねしていません", self.post_id)
            
            # いいね解除を実行
            success = sns_manager.unlike_post(player_id, self.post_id)
            if success:
                return SnsUnlikeResult(True, "投稿のいいねを解除しました", self.post_id)
            else:
                return SnsUnlikeResult(False, "いいね解除に失敗しました", self.post_id)
        except Exception as e:
            return SnsUnlikeResult(False, f"いいね解除中にエラーが発生しました: {e}", self.post_id)


class SnsReplyCommand(ActionCommand):
    def __init__(self, post_id: str, content: str):
        super().__init__("SNS投稿に返信")
        self.post_id = post_id
        self.content = content

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsReplyResult:
        player_id = acting_player.get_player_id()
        sns_manager = game_context.get_sns_manager()
        
        try:
            # 投稿が存在するかチェック
            post = sns_manager.get_post(self.post_id)
            if post is None:
                return SnsReplyResult(False, f"投稿ID {self.post_id} が見つかりません", self.post_id, "")
            
            # 返信内容が空でないかチェック
            if not self.content.strip():
                return SnsReplyResult(False, "返信内容が空です", self.post_id, "")
            
            # 返信を実行
            reply = sns_manager.reply_to_post(player_id, self.post_id, self.content)
            if reply:
                return SnsReplyResult(True, "投稿に返信しました", self.post_id, reply.reply_id)
            else:
                return SnsReplyResult(False, "返信に失敗しました", self.post_id, "")
        except Exception as e:
            return SnsReplyResult(False, f"返信中にエラーが発生しました: {e}", self.post_id, "")


class SnsGetNotificationsCommand(ActionCommand):
    def __init__(self, unread_only: bool = False):
        super().__init__("SNS通知取得")
        self.unread_only = unread_only

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsGetNotificationsResult:
        player_id = acting_player.get_player_id()
        sns_manager = game_context.get_sns_manager()
        
        try:
            # 通知を取得
            notifications = sns_manager.get_user_notifications(player_id, unread_only=self.unread_only)
            
            # 通知を文字列形式に変換
            notification_strings = []
            for notification in notifications:
                status = "📬" if notification.is_read else "📨"
                notification_str = f"{status} {notification.content} (ID: {notification.notification_id})"
                notification_strings.append(notification_str)
            
            if not notification_strings:
                message = "未読通知がありません" if self.unread_only else "通知がありません"
                return SnsGetNotificationsResult(True, message, [])
            else:
                return SnsGetNotificationsResult(True, f"{len(notification_strings)}件の通知を取得しました", notification_strings)
        except Exception as e:
            return SnsGetNotificationsResult(False, f"通知取得中にエラーが発生しました: {e}", [])


class SnsMarkNotificationReadCommand(ActionCommand):
    def __init__(self, notification_id: str):
        super().__init__("SNS通知を既読にする")
        self.notification_id = notification_id

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsMarkNotificationReadResult:
        sns_manager = game_context.get_sns_manager()
        
        try:
            # 通知を既読にする
            success = sns_manager.mark_notification_as_read(self.notification_id)
            if success:
                return SnsMarkNotificationReadResult(True, "通知を既読にしました", self.notification_id)
            else:
                return SnsMarkNotificationReadResult(False, "通知が見つからないか、既に既読です", self.notification_id)
        except Exception as e:
            return SnsMarkNotificationReadResult(False, f"既読処理中にエラーが発生しました: {e}", self.notification_id)


# ===== 状態遷移関連の行動 =====

class SnsOpenResult(ActionResult):
    """SNSを開く結果"""
    def __init__(self, success: bool, message: str):
        super().__init__(success, message)
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} はSNSを開きました"
        else:
            return f"{player_name} はSNSを開けませんでした\n\t理由:{self.message}"


class SnsCloseResult(ActionResult):
    """SNSを閉じる結果"""
    def __init__(self, success: bool, message: str):
        super().__init__(success, message)
        
    def to_feedback_message(self, player_name: str) -> str:
        if self.success:
            return f"{player_name} はSNSを閉じました"
        else:
            return f"{player_name} はSNSを閉じることができませんでした\n\t理由:{self.message}"


class SnsOpenCommand(ActionCommand):
    """SNSを開くコマンド"""
    
    def __init__(self):
        pass

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsOpenResult:
        # プレイヤーの状態をSNSに変更
        acting_player.set_player_state(PlayerState.SNS)
        return SnsOpenResult(True, "SNSを開きました")


class SnsCloseCommand(ActionCommand):
    """SNSを閉じるコマンド"""
    
    def __init__(self):
        pass

    def execute(self, acting_player: Player, game_context: GameContext) -> SnsCloseResult:
        # プレイヤーの状態を通常に変更
        acting_player.set_player_state(PlayerState.NORMAL)
        return SnsCloseResult(True, "SNSを閉じました")


class SnsOpenStrategy(ActionStrategy):
    """SNSを開く戦略"""
    
    def __init__(self):
        super().__init__("SNSを開く")
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # 通常状態の時のみSNSを開ける
        return acting_player.is_in_normal_state()
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> SnsOpenCommand:
        return SnsOpenCommand()


class SnsCloseStrategy(ActionStrategy):
    """SNSを閉じる戦略"""
    
    def __init__(self):
        super().__init__("SNSを閉じる")
    
    def can_execute(self, acting_player: Player, game_context: GameContext) -> bool:
        # SNS状態の時のみSNSを閉じられる
        return acting_player.is_in_sns_state()
    
    def get_required_arguments(self, acting_player: Player, game_context: GameContext) -> List[ArgumentInfo]:
        return []
    
    def build_action_command(self, acting_player: Player, game_context: GameContext, **kwargs) -> SnsCloseCommand:
        return SnsCloseCommand()