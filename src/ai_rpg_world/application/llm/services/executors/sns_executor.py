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
    TOOL_NAME_SNS_OPEN_PAGE,
    TOOL_NAME_SNS_OPEN_REF,
    TOOL_NAME_SNS_PAGE_NEXT,
    TOOL_NAME_SNS_PAGE_REFRESH,
    TOOL_NAME_SNS_SUBSCRIBE,
    TOOL_NAME_SNS_SWITCH_TAB,
    TOOL_NAME_SNS_UNBLOCK,
    TOOL_NAME_SNS_UNFOLLOW,
    TOOL_NAME_SNS_UNSUBSCRIBE,
    TOOL_NAME_SNS_UPDATE_PROFILE,
    TOOL_NAME_SNS_VIEW_CURRENT_PAGE,
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
from ai_rpg_world.application.social.contracts.dtos import NotificationDto
from ai_rpg_world.application.social.sns_virtual_pages.kinds import (
    SnsHomeTab,
    SnsSearchMode,
    SnsVirtualPageKind,
)
from ai_rpg_world.application.social.sns_virtual_pages.snapshot_json import sns_snapshot_to_json
from ai_rpg_world.domain.sns.enum import PostVisibility


def _parse_sns_virtual_page_kind(raw: Any) -> Optional[SnsVirtualPageKind]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    for k in SnsVirtualPageKind:
        if k.value == s:
            return k
    return None


def _parse_sns_home_tab(raw: Any) -> SnsHomeTab:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return SnsHomeTab.FOLLOWING
    t = str(raw).strip().lower()
    if t == SnsHomeTab.POPULAR.value:
        return SnsHomeTab.POPULAR
    return SnsHomeTab.FOLLOWING


def _parse_sns_search_mode(raw: Any) -> Optional[SnsSearchMode]:
    if raw is None:
        return None
    t = str(raw).strip().lower()
    if t == SnsSearchMode.HASHTAG.value:
        return SnsSearchMode.HASHTAG
    return SnsSearchMode.KEYWORD


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
        sns_page_session: Optional[Any] = None,
        sns_page_query_service: Optional[Any] = None,
        reply_query_service: Optional[Any] = None,
        notification_query_service: Optional[Any] = None,
    ) -> None:
        self._post_service = post_service
        self._reply_service = reply_service
        self._user_command_service = user_command_service
        self._notification_command_service = notification_command_service
        self._sns_mode_session = sns_mode_session
        self._sns_page_session = sns_page_session
        self._sns_page_query_service = sns_page_query_service
        self._reply_query_service = reply_query_service
        self._notification_query_service = notification_query_service

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
        if self._sns_page_query_service is not None and self._sns_page_session is not None:
            handlers[TOOL_NAME_SNS_VIEW_CURRENT_PAGE] = self._execute_view_current_page
            handlers[TOOL_NAME_SNS_PAGE_REFRESH] = self._execute_page_refresh
            handlers[TOOL_NAME_SNS_OPEN_PAGE] = self._execute_open_page
            handlers[TOOL_NAME_SNS_OPEN_REF] = self._execute_open_ref
            handlers[TOOL_NAME_SNS_PAGE_NEXT] = self._execute_page_next
            handlers[TOOL_NAME_SNS_SWITCH_TAB] = self._execute_switch_tab
        return handlers

    def _execute_sns_enter(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_mode_session is None:
            return unknown_tool("SNS モード状態が利用できません。")
        self._sns_mode_session.enter_sns_mode(player_id)
        if self._sns_page_session is not None:
            self._sns_page_session.on_enter_sns(player_id)
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
        if self._sns_page_session is not None:
            self._sns_page_session.on_exit_sns(player_id)
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
                MarkNotificationAsReadCommand(
                    user_id=player_id,
                    notification_id=int(notification_id),
                )
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

    def _find_notification_by_id(
        self, user_id: int, notification_id: int
    ) -> Optional[NotificationDto]:
        if self._notification_query_service is None:
            return None
        offset = 0
        batch_size = 100
        while offset < 5000:
            batch = self._notification_query_service.get_user_notifications(
                user_id, limit=batch_size, offset=offset
            )
            for n in batch:
                if n.notification_id == notification_id:
                    return n
            if len(batch) < batch_size:
                break
            offset += batch_size
        return None

    def _snapshot_message(self, player_id: int) -> str:
        assert self._sns_page_query_service is not None
        snap = self._sns_page_query_service.get_current_page_snapshot(
            player_id=player_id,
            viewer_user_id=player_id,
        )
        return sns_snapshot_to_json(snap)

    def _execute_view_current_page(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_page_query_service is None:
            return unknown_tool("仮想 SNS 画面が利用できません。")
        try:
            text = self._snapshot_message(player_id)
            return LlmCommandResultDto(success=True, message=text)
        except Exception as e:
            return exception_result(e)

    def _execute_page_refresh(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        return self._execute_view_current_page(player_id, args)

    def _execute_open_page(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_page_session is None or self._sns_page_query_service is None:
            return unknown_tool("仮想 SNS 画面が利用できません。")
        kind = _parse_sns_virtual_page_kind(args.get("page"))
        if kind is None:
            return invalid_arg_result("page")
        sess = self._sns_page_session
        try:
            if kind == SnsVirtualPageKind.HOME:
                tab = _parse_sns_home_tab(args.get("home_tab"))
                sess.set_page_kind(player_id, SnsVirtualPageKind.HOME)
                sess.set_home_tab(player_id, tab)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="ホームへ遷移しました。")
            if kind == SnsVirtualPageKind.POST_DETAIL:
                post_ref = args.get("post_ref")
                if post_ref is None or not str(post_ref).strip():
                    return invalid_arg_result("post_ref")
                pid = sess.resolve_post_ref(player_id, str(post_ref).strip())
                if pid is None:
                    return LlmCommandResultDto(
                        success=False,
                        message="post_ref が無効か、古い世代です。画面を再取得してください。",
                    )
                sess.set_page_kind(player_id, SnsVirtualPageKind.POST_DETAIL)
                sess.set_post_detail_root_post_id(player_id, pid)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="投稿詳細へ遷移しました。")
            if kind == SnsVirtualPageKind.SEARCH:
                mode = _parse_sns_search_mode(args.get("search_mode"))
                q = args.get("search_query")
                query_str = str(q).strip() if q is not None else ""
                sess.set_page_kind(player_id, SnsVirtualPageKind.SEARCH)
                sess.set_search_context(player_id, mode=mode, query=query_str)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="検索画面へ遷移しました。")
            if kind == SnsVirtualPageKind.PROFILE:
                ref = args.get("profile_user_ref")
                if ref is None or not str(ref).strip():
                    sess.set_page_kind(player_id, SnsVirtualPageKind.PROFILE)
                    sess.set_profile_target_user_id(player_id, None)
                    sess.set_paging(player_id, offset=0)
                    return LlmCommandResultDto(success=True, message="自分のプロフィールへ遷移しました。")
                uid = sess.resolve_user_ref(player_id, str(ref).strip())
                if uid is None:
                    return LlmCommandResultDto(
                        success=False,
                        message="profile_user_ref が無効か、古い世代です。",
                    )
                sess.set_page_kind(player_id, SnsVirtualPageKind.PROFILE)
                sess.set_profile_target_user_id(player_id, uid)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="プロフィールへ遷移しました。")
            if kind == SnsVirtualPageKind.NOTIFICATIONS:
                sess.set_page_kind(player_id, SnsVirtualPageKind.NOTIFICATIONS)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="通知一覧へ遷移しました。")
        except Exception as e:
            return exception_result(e)
        return LlmCommandResultDto(success=False, message="未対応の画面です。")

    def _execute_open_ref(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_page_session is None or self._sns_page_query_service is None:
            return unknown_tool("仮想 SNS 画面が利用できません。")
        ref = args.get("ref")
        if ref is None or not str(ref).strip():
            return invalid_arg_result("ref")
        ref_s = str(ref).strip()
        sess = self._sns_page_session
        try:
            pid = sess.resolve_post_ref(player_id, ref_s)
            if pid is not None:
                sess.set_page_kind(player_id, SnsVirtualPageKind.POST_DETAIL)
                sess.set_post_detail_root_post_id(player_id, pid)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="投稿詳細へ遷移しました。")
            uid = sess.resolve_user_ref(player_id, ref_s)
            if uid is not None:
                sess.set_page_kind(player_id, SnsVirtualPageKind.PROFILE)
                sess.set_profile_target_user_id(player_id, uid)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="プロフィールへ遷移しました。")
            rid = sess.resolve_reply_ref(player_id, ref_s)
            if rid is not None:
                if self._reply_query_service is None:
                    return unknown_tool("リプライ参照を解決できません。")
                r = self._reply_query_service.get_reply_by_id(rid, player_id)
                if r is None:
                    return LlmCommandResultDto(success=False, message="リプライが見つかりません。")
                root = r.parent_post_id
                if root is None:
                    return LlmCommandResultDto(
                        success=False,
                        message="リプライの親投稿を特定できません。",
                    )
                sess.set_page_kind(player_id, SnsVirtualPageKind.POST_DETAIL)
                sess.set_post_detail_root_post_id(player_id, root)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="投稿詳細へ遷移しました。")
            nid = sess.resolve_notification_ref(player_id, ref_s)
            if nid is not None:
                n = self._find_notification_by_id(player_id, nid)
                if n is None:
                    return LlmCommandResultDto(
                        success=False,
                        message="通知が見つからないか、一覧の範囲外です。",
                    )
                if n.related_post_id is not None:
                    sess.set_page_kind(player_id, SnsVirtualPageKind.POST_DETAIL)
                    sess.set_post_detail_root_post_id(player_id, n.related_post_id)
                    sess.set_paging(player_id, offset=0)
                    return LlmCommandResultDto(success=True, message="投稿詳細へ遷移しました。")
                if n.related_reply_id is not None and self._reply_query_service is not None:
                    r = self._reply_query_service.get_reply_by_id(
                        n.related_reply_id, player_id
                    )
                    if r is not None and r.parent_post_id is not None:
                        sess.set_page_kind(player_id, SnsVirtualPageKind.POST_DETAIL)
                        sess.set_post_detail_root_post_id(player_id, r.parent_post_id)
                        sess.set_paging(player_id, offset=0)
                        return LlmCommandResultDto(success=True, message="投稿詳細へ遷移しました。")
                sess.set_page_kind(player_id, SnsVirtualPageKind.PROFILE)
                sess.set_profile_target_user_id(player_id, n.actor_user_id)
                sess.set_paging(player_id, offset=0)
                return LlmCommandResultDto(success=True, message="プロフィールへ遷移しました。")
        except Exception as e:
            return exception_result(e)
        return LlmCommandResultDto(
            success=False,
            message="ref が解決できません。スナップショットを再取得し、有効な ref を指定してください。",
        )

    def _execute_page_next(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_page_session is None:
            return unknown_tool("仮想 SNS 画面が利用できません。")
        try:
            st = self._sns_page_session.get_state(player_id)
            new_offset = st.offset + st.limit
            self._sns_page_session.set_paging(player_id, offset=new_offset)
            return LlmCommandResultDto(success=True, message="次ページへ進めました。")
        except Exception as e:
            return exception_result(e)

    def _execute_switch_tab(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._sns_page_session is None:
            return unknown_tool("仮想 SNS 画面が利用できません。")
        raw_tab = args.get("tab")
        if raw_tab is None or not str(raw_tab).strip():
            return invalid_arg_result("tab")
        tab = _parse_sns_home_tab(raw_tab)
        st = self._sns_page_session.get_state(player_id)
        if st.page_kind != SnsVirtualPageKind.HOME:
            return LlmCommandResultDto(
                success=False,
                message="home 画面でのみタブを切り替えられます。",
            )
        try:
            self._sns_page_session.set_home_tab(player_id, tab)
            self._sns_page_session.set_paging(player_id, offset=0)
            return LlmCommandResultDto(success=True, message="タブを切り替えました。")
        except Exception as e:
            return exception_result(e)
