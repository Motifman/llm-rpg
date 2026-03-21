"""SNS ツール（create_post, create_reply, like_post, like_reply, follow, block 等）の実行。"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    invalid_arg_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SNS_BLOCK,
    TOOL_NAME_SNS_CREATE_POST,
    TOOL_NAME_SNS_CREATE_REPLY,
    TOOL_NAME_SNS_DELETE_POST,
    TOOL_NAME_SNS_DELETE_REPLY,
    TOOL_NAME_SNS_ENTER,
    TOOL_NAME_SNS_FOLLOW,
    TOOL_NAME_SNS_LIKE_POST,
    TOOL_NAME_SNS_LIKE_REPLY,
    TOOL_NAME_SNS_LOGOUT,
    TOOL_NAME_SNS_MARK_ALL_NOTIFICATIONS_READ,
    TOOL_NAME_SNS_MARK_NOTIFICATION_READ,
    TOOL_NAME_SNS_SUBSCRIBE,
    TOOL_NAME_SNS_UNBLOCK,
    TOOL_NAME_SNS_UNFOLLOW,
    TOOL_NAME_SNS_UNSUBSCRIBE,
    TOOL_NAME_SNS_UPDATE_PROFILE,
)
from ai_rpg_world.application.social.contracts.commands import (
    BlockUserCommand,
    CreatePostCommand,
    CreateReplyCommand,
    DeletePostCommand,
    DeleteReplyCommand,
    FollowUserCommand,
    LikePostCommand,
    LikeReplyCommand,
    MarkAllNotificationsAsReadCommand,
    MarkNotificationAsReadCommand,
    SubscribeUserCommand,
    UnblockUserCommand,
    UnfollowUserCommand,
    UnsubscribeUserCommand,
    UpdateUserProfileCommand,
)
from ai_rpg_world.domain.sns.enum import PostVisibility


class SnsToolExecutor:
    """
    SNS ツールの実行を担当するサブマッパー。
    player_id と user_id は 1:1 対応を前提とする。

    各サービスは Optional で、None の場合は該当ツールをハンドラに登録しない。
    期待するインターフェース:
    - post_service: create_post(user_id, content, visibility), like_post(post_id, user_id)
    - reply_service: create_reply(...), like_reply(reply_id, user_id)
    - user_command_service: follow_user, unfollow_user, subscribe_user, unsubscribe_user, block_user, unblock_user
    """

    def __init__(
        self,
        post_service: Optional[Any] = None,
        reply_service: Optional[Any] = None,
        user_command_service: Optional[Any] = None,
        notification_command_service: Optional[Any] = None,
        sns_mode_session: Optional[Any] = None,
    ) -> None:
        self._post_service = post_service
        self._reply_service = reply_service
        self._user_command_service = user_command_service
        self._notification_command_service = notification_command_service
        self._sns_mode_session = sns_mode_session

    def get_handlers(
        self,
    ) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。"""
        handlers: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]] = {}
        handlers[TOOL_NAME_SNS_ENTER] = self._execute_sns_enter
        handlers[TOOL_NAME_SNS_LOGOUT] = self._execute_sns_logout
        if self._post_service is not None:
            handlers[TOOL_NAME_SNS_CREATE_POST] = self._execute_create_post
            handlers[TOOL_NAME_SNS_LIKE_POST] = self._execute_like_post
            handlers[TOOL_NAME_SNS_DELETE_POST] = self._execute_delete_post
        if self._reply_service is not None:
            handlers[TOOL_NAME_SNS_CREATE_REPLY] = self._execute_create_reply
            handlers[TOOL_NAME_SNS_LIKE_REPLY] = self._execute_like_reply
            handlers[TOOL_NAME_SNS_DELETE_REPLY] = self._execute_delete_reply
        if self._user_command_service is not None:
            handlers[TOOL_NAME_SNS_UPDATE_PROFILE] = self._execute_update_profile
            handlers[TOOL_NAME_SNS_FOLLOW] = self._execute_follow
            handlers[TOOL_NAME_SNS_UNFOLLOW] = self._execute_unfollow
            handlers[TOOL_NAME_SNS_SUBSCRIBE] = self._execute_subscribe
            handlers[TOOL_NAME_SNS_UNSUBSCRIBE] = self._execute_unsubscribe
            handlers[TOOL_NAME_SNS_BLOCK] = self._execute_block
            handlers[TOOL_NAME_SNS_UNBLOCK] = self._execute_unblock
        if self._notification_command_service is not None:
            handlers[TOOL_NAME_SNS_MARK_NOTIFICATION_READ] = self._execute_mark_notification_read
            handlers[TOOL_NAME_SNS_MARK_ALL_NOTIFICATIONS_READ] = (
                self._execute_mark_all_notifications_read
            )
        return handlers

    def _execute_sns_enter(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_mode_session is None:
            return unknown_tool("SNS モード状態が利用できません。")
        self._sns_mode_session.enter_sns_mode(player_id)
        return LlmCommandResultDto(
            success=True,
            message="ゲーム内 SNS を開きました。",
        )

    def _execute_sns_logout(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_mode_session is None:
            return unknown_tool("SNS モード状態が利用できません。")
        self._sns_mode_session.exit_sns_mode(player_id)
        return LlmCommandResultDto(
            success=True,
            message="ゲーム内 SNS を閉じました。",
        )

    def _execute_delete_post(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._post_service is None:
            return unknown_tool("ポスト削除ツールはまだ利用できません。")
        post_id = args.get("post_id")
        if post_id is None:
            return invalid_arg_result("post_id")
        try:
            result = self._post_service.delete_post(
                DeletePostCommand(post_id=int(post_id), user_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_delete_reply(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._reply_service is None:
            return unknown_tool("リプライ削除ツールはまだ利用できません。")
        reply_id = args.get("reply_id")
        if reply_id is None:
            return invalid_arg_result("reply_id")
        try:
            result = self._reply_service.delete_reply(
                DeleteReplyCommand(reply_id=int(reply_id), user_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_update_profile(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._user_command_service is None:
            return unknown_tool("プロフィール更新ツールはまだ利用できません。")
        raw_name = args.get("new_display_name")
        raw_bio = args.get("new_bio")
        new_display_name: Optional[str]
        new_bio: Optional[str]
        if raw_name is None:
            new_display_name = None
        else:
            new_display_name = str(raw_name).strip() or None
        if raw_bio is None:
            new_bio = None
        else:
            new_bio = str(raw_bio).strip() or None
        if new_display_name is None and new_bio is None:
            return invalid_arg_result("new_display_name または new_bio")
        try:
            result = self._user_command_service.update_user_profile(
                UpdateUserProfileCommand(
                    user_id=player_id,
                    new_display_name=new_display_name,
                    new_bio=new_bio,
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_mark_notification_read(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._notification_command_service is None:
            return unknown_tool("通知既読ツールはまだ利用できません。")
        notification_id = args.get("notification_id")
        if notification_id is None:
            return invalid_arg_result("notification_id")
        try:
            result = self._notification_command_service.mark_notification_as_read(
                MarkNotificationAsReadCommand(notification_id=int(notification_id))
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_mark_all_notifications_read(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._notification_command_service is None:
            return unknown_tool("通知一括既読ツールはまだ利用できません。")
        try:
            result = self._notification_command_service.mark_all_notifications_as_read(
                MarkAllNotificationsAsReadCommand(user_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _parse_visibility(self, raw: Any) -> tuple[PostVisibility, bool]:
        """
        visibility 文字列を PostVisibility に変換。
        省略時・不明な値は public（公開）をデフォルトとする。
        Returns:
            (PostVisibility, should_hint): LLM にヒントを出すべきか（値指定ありかつ不明な場合）
        """
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return PostVisibility.PUBLIC, False  # 省略時はヒント不要
        s = str(raw).strip().lower()
        if s in ("public", "公開"):
            return PostVisibility.PUBLIC, False
        if s in ("followers_only", "followers", "フォロワー限定"):
            return PostVisibility.FOLLOWERS_ONLY, False
        if s in ("private", "プライベート"):
            return PostVisibility.PRIVATE, False
        return PostVisibility.PUBLIC, True  # 不明な値指定時はヒントを出す

    def _execute_create_post(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._post_service is None:
            return unknown_tool("投稿作成ツールはまだ利用できません。")
        content = args.get("content")
        if content is None or (isinstance(content, str) and not content.strip()):
            return invalid_arg_result("content")
        try:
            visibility, visibility_defaulted = self._parse_visibility(args.get("visibility"))
            result = self._post_service.create_post(
                CreatePostCommand(
                    user_id=player_id,
                    content=str(content).strip(),
                    visibility=visibility,
                )
            )
            msg = result.message
            if result.success and visibility_defaulted:
                msg += " （公開範囲: public。不明な値は public として扱いました。正しい値: public, followers_only, private）"
            return LlmCommandResultDto(success=result.success, message=msg)
        except Exception as e:
            return exception_result(e)

    def _execute_create_reply(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._reply_service is None:
            return unknown_tool("リプライ作成ツールはまだ利用できません。")
        content = args.get("content")
        if content is None or (isinstance(content, str) and not content.strip()):
            return invalid_arg_result("content")
        parent_post_id = args.get("parent_post_id")
        parent_reply_id = args.get("parent_reply_id")
        if parent_post_id is None and parent_reply_id is None:
            return invalid_arg_result("parent_post_id または parent_reply_id")
        try:
            visibility, visibility_defaulted = self._parse_visibility(args.get("visibility"))
            result = self._reply_service.create_reply(
                CreateReplyCommand(
                    user_id=player_id,
                    content=str(content).strip(),
                    visibility=visibility,
                    parent_post_id=int(parent_post_id) if parent_post_id is not None else None,
                    parent_reply_id=int(parent_reply_id) if parent_reply_id is not None else None,
                )
            )
            msg = result.message
            if result.success and visibility_defaulted:
                msg += " （公開範囲: public。不明な値は public として扱いました。正しい値: public, followers_only, private）"
            return LlmCommandResultDto(success=result.success, message=msg)
        except Exception as e:
            return exception_result(e)

    def _execute_like_post(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._post_service is None:
            return unknown_tool("ポストいいねツールはまだ利用できません。")
        post_id = args.get("post_id")
        if post_id is None:
            return invalid_arg_result("post_id")
        try:
            result = self._post_service.like_post(
                LikePostCommand(post_id=int(post_id), user_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_like_reply(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._reply_service is None:
            return unknown_tool("リプライいいねツールはまだ利用できません。")
        reply_id = args.get("reply_id")
        if reply_id is None:
            return invalid_arg_result("reply_id")
        try:
            result = self._reply_service.like_reply(
                LikeReplyCommand(reply_id=int(reply_id), user_id=player_id)
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_follow(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._user_command_service is None:
            return unknown_tool("フォローツールはまだ利用できません。")
        target_user_id = args.get("target_user_id")
        if target_user_id is None:
            return invalid_arg_result("target_user_id")
        try:
            result = self._user_command_service.follow_user(
                FollowUserCommand(
                    follower_user_id=player_id,
                    followee_user_id=int(target_user_id),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_unfollow(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._user_command_service is None:
            return unknown_tool("フォロー解除ツールはまだ利用できません。")
        target_user_id = args.get("target_user_id")
        if target_user_id is None:
            return invalid_arg_result("target_user_id")
        try:
            result = self._user_command_service.unfollow_user(
                UnfollowUserCommand(
                    follower_user_id=player_id,
                    followee_user_id=int(target_user_id),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_subscribe(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._user_command_service is None:
            return unknown_tool("サブスクライブツールはまだ利用できません。")
        target_user_id = args.get("target_user_id")
        if target_user_id is None:
            return invalid_arg_result("target_user_id")
        try:
            result = self._user_command_service.subscribe_user(
                SubscribeUserCommand(
                    subscriber_user_id=player_id,
                    subscribed_user_id=int(target_user_id),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_unsubscribe(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._user_command_service is None:
            return unknown_tool("サブスクライブ解除ツールはまだ利用できません。")
        target_user_id = args.get("target_user_id")
        if target_user_id is None:
            return invalid_arg_result("target_user_id")
        try:
            result = self._user_command_service.unsubscribe_user(
                UnsubscribeUserCommand(
                    subscriber_user_id=player_id,
                    subscribed_user_id=int(target_user_id),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_block(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._user_command_service is None:
            return unknown_tool("ブロックツールはまだ利用できません。")
        target_user_id = args.get("target_user_id")
        if target_user_id is None:
            return invalid_arg_result("target_user_id")
        try:
            result = self._user_command_service.block_user(
                BlockUserCommand(
                    blocker_user_id=player_id,
                    blocked_user_id=int(target_user_id),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)

    def _execute_unblock(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._user_command_service is None:
            return unknown_tool("ブロック解除ツールはまだ利用できません。")
        target_user_id = args.get("target_user_id")
        if target_user_id is None:
            return invalid_arg_result("target_user_id")
        try:
            result = self._user_command_service.unblock_user(
                UnblockUserCommand(
                    blocker_user_id=player_id,
                    blocked_user_id=int(target_user_id),
                )
            )
            return LlmCommandResultDto(success=result.success, message=result.message)
        except Exception as e:
            return exception_result(e)
