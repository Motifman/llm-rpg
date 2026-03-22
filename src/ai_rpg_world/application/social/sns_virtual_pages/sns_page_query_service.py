"""既存 query service を束ね、page session の ref とともに画面スナップショットを組み立てる。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from ai_rpg_world.application.social.contracts.dtos import (
    NotificationDto,
    PostDto,
    ReplyDto,
    UserProfileDto,
)
from ai_rpg_world.application.social.sns_virtual_pages.kinds import (
    SnsHomeTab,
    SnsSearchMode,
    SnsVirtualPageKind,
)
from ai_rpg_world.application.social.sns_virtual_pages.page_session_state import (
    SnsPageSessionState,
)
from ai_rpg_world.application.social.sns_virtual_pages.page_snapshot_dtos import (
    SnsHomeSnapshotDto,
    SnsNotificationLineSnapshotDto,
    SnsNotificationsSnapshotDto,
    SnsPagingSnapshotDto,
    SnsPostDetailSnapshotDto,
    SnsPostLineSnapshotDto,
    SnsProfileHeaderSnapshotDto,
    SnsProfileSnapshotDto,
    SnsReplyLineSnapshotDto,
    SnsSearchSnapshotDto,
    SnsVirtualPageSnapshotDto,
)
from ai_rpg_world.application.social.sns_virtual_pages.sns_page_session_service import (
    SnsPageSessionService,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.social.services.notification_query_service import (
        NotificationQueryService,
    )
    from ai_rpg_world.application.social.services.post_query_service import PostQueryService
    from ai_rpg_world.application.social.services.reply_query_service import ReplyQueryService
    from ai_rpg_world.application.social.services.user_query_service import UserQueryService

_CONTENT_PREVIEW_MAX = 200
_POPULAR_TIMEFRAME_HOURS = 24
_TRENDING_HASHTAGS_LIMIT = 10


def _preview_content(content: str, max_len: int = _CONTENT_PREVIEW_MAX) -> str:
    s = (content or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _slice_page(raw: List[Any], limit: int) -> Tuple[List[Any], bool]:
    """limit+1 件取得想定で has_more を付与。"""
    if len(raw) > limit:
        return raw[:limit], True
    return raw, False


class SnsPageQueryService:
    """SnsPageSessionState に従い、各画面の読み取りスナップショットを組み立てる。"""

    def __init__(
        self,
        post_query: "PostQueryService",
        reply_query: "ReplyQueryService",
        notification_query: "NotificationQueryService",
        user_query: "UserQueryService",
        page_session: SnsPageSessionService,
    ) -> None:
        self._post_query = post_query
        self._reply_query = reply_query
        self._notification_query = notification_query
        self._user_query = user_query
        self._page_session = page_session

    def get_current_page_snapshot(
        self,
        player_id: int,
        viewer_user_id: int,
    ) -> SnsVirtualPageSnapshotDto:
        """現在の page session に対応するスナップショットを返す。取得のたびに ref 世代を更新する。"""
        gen = self._page_session.bump_snapshot_generation(player_id)
        st = self._page_session.get_state(player_id)
        kind = st.page_kind

        if kind == SnsVirtualPageKind.HOME:
            return self._snapshot_home(player_id, viewer_user_id, st, gen)
        if kind == SnsVirtualPageKind.POST_DETAIL:
            return self._snapshot_post_detail(player_id, viewer_user_id, st, gen)
        if kind == SnsVirtualPageKind.SEARCH:
            return self._snapshot_search(player_id, viewer_user_id, st, gen)
        if kind == SnsVirtualPageKind.PROFILE:
            return self._snapshot_profile(player_id, viewer_user_id, st, gen)
        if kind == SnsVirtualPageKind.NOTIFICATIONS:
            return self._snapshot_notifications(player_id, viewer_user_id, st, gen)

        raise RuntimeError(f"unsupported page kind: {kind!r}")

    def _paging(self, st: SnsPageSessionState, has_more: bool) -> SnsPagingSnapshotDto:
        return SnsPagingSnapshotDto(offset=st.offset, limit=st.limit, has_more=has_more)

    def _post_line(
        self,
        player_id: int,
        post: PostDto,
        *,
        include_author_ref: bool = True,
    ) -> SnsPostLineSnapshotDto:
        post_ref = self._page_session.issue_post_ref(player_id, post.post_id)
        author_ref: Optional[str] = None
        if include_author_ref and not post.is_deleted:
            author_ref = self._page_session.issue_user_ref(player_id, post.author_user_id)
        return SnsPostLineSnapshotDto(
            author_display_name=post.author_display_name,
            content_preview=_preview_content(post.content),
            created_at=post.created_at,
            like_count=post.like_count,
            reply_count=post.reply_count,
            is_liked_by_viewer=post.is_liked_by_viewer,
            is_replied_by_viewer=post.is_replied_by_viewer,
            post_ref=post_ref,
            author_user_ref=author_ref,
        )

    def _snapshot_home(
        self,
        player_id: int,
        viewer_user_id: int,
        st: SnsPageSessionState,
        gen: int,
    ) -> SnsVirtualPageSnapshotDto:
        lim = st.limit + 1
        trending: List[str] = []
        if st.home_tab == SnsHomeTab.FOLLOWING:
            raw = self._post_query.get_home_timeline(
                viewer_user_id, limit=lim, offset=st.offset
            )
            posts, has_more = _slice_page(raw, st.limit)
        elif st.home_tab == SnsHomeTab.POPULAR:
            raw = self._post_query.get_popular_posts(
                viewer_user_id,
                timeframe_hours=_POPULAR_TIMEFRAME_HOURS,
                limit=lim,
                offset=st.offset,
            )
            posts, has_more = _slice_page(raw, st.limit)
            trending = self._post_query.get_trending_hashtags(
                limit=_TRENDING_HASHTAGS_LIMIT
            )
        else:
            posts, has_more = [], False

        lines = [self._post_line(player_id, p) for p in posts]
        body = SnsHomeSnapshotDto(
            active_tab=st.home_tab,
            posts=lines,
            trending_hashtags=trending,
        )
        return SnsVirtualPageSnapshotDto(
            page_kind=SnsVirtualPageKind.HOME,
            snapshot_generation=gen,
            paging=self._paging(st, has_more),
            home=body,
        )

    def _snapshot_post_detail(
        self,
        player_id: int,
        viewer_user_id: int,
        st: SnsPageSessionState,
        gen: int,
    ) -> SnsVirtualPageSnapshotDto:
        root_id = st.post_detail_root_post_id
        if root_id is None:
            return SnsVirtualPageSnapshotDto(
                page_kind=SnsVirtualPageKind.POST_DETAIL,
                snapshot_generation=gen,
                paging=SnsPagingSnapshotDto(offset=0, limit=1, has_more=False),
                error="post_detail_root_post_id が未設定です",
            )

        thread = self._reply_query.get_reply_thread(root_id, viewer_user_id)
        root_line = self._post_line(player_id, thread.post)
        reply_lines: List[SnsReplyLineSnapshotDto] = []
        for r in thread.replies:
            rr = self._page_session.issue_reply_ref(player_id, r.reply_id)
            author_ref: Optional[str] = None
            if not r.is_deleted:
                author_ref = self._page_session.issue_user_ref(player_id, r.author_user_id)
            reply_lines.append(
                SnsReplyLineSnapshotDto(
                    author_display_name=r.author_display_name,
                    content_preview=_preview_content(r.content),
                    created_at=r.created_at,
                    depth=r.depth,
                    like_count=r.like_count,
                    reply_count=r.reply_count,
                    is_liked_by_viewer=r.is_liked_by_viewer,
                    reply_ref=rr,
                    author_user_ref=author_ref,
                )
            )
        body = SnsPostDetailSnapshotDto(root_post=root_line, replies=reply_lines)
        return SnsVirtualPageSnapshotDto(
            page_kind=SnsVirtualPageKind.POST_DETAIL,
            snapshot_generation=gen,
            paging=SnsPagingSnapshotDto(offset=0, limit=1, has_more=False),
            post_detail=body,
        )

    def _snapshot_search(
        self,
        player_id: int,
        viewer_user_id: int,
        st: SnsPageSessionState,
        gen: int,
    ) -> SnsVirtualPageSnapshotDto:
        lim = st.limit + 1
        q = (st.search_query or "").strip()
        mode = st.search_mode
        raw: List[PostDto] = []
        if not q:
            raw = []
        elif mode == SnsSearchMode.HASHTAG:
            raw = self._post_query.search_posts_by_hashtag(
                q, viewer_user_id, limit=lim, offset=st.offset
            )
        else:
            raw = self._post_query.search_posts_by_keyword(
                q, viewer_user_id, limit=lim, offset=st.offset
            )

        posts, has_more = _slice_page(raw, st.limit)
        lines = [self._post_line(player_id, p) for p in posts]
        body = SnsSearchSnapshotDto(
            search_mode=mode,
            search_query=st.search_query,
            posts=lines,
        )
        return SnsVirtualPageSnapshotDto(
            page_kind=SnsVirtualPageKind.SEARCH,
            snapshot_generation=gen,
            paging=self._paging(st, has_more),
            search=body,
        )

    def _profile_header_from_dto(
        self,
        player_id: int,
        profile: UserProfileDto,
        *,
        viewer_user_id: int,
    ) -> SnsProfileHeaderSnapshotDto:
        is_self = profile.user_id == viewer_user_id
        subject_ref: Optional[str] = None
        if not is_self:
            subject_ref = self._page_session.issue_user_ref(player_id, profile.user_id)
        return SnsProfileHeaderSnapshotDto(
            display_name=profile.display_name,
            user_name=profile.user_name,
            bio=profile.bio,
            is_self=is_self,
            followee_count=profile.followee_count,
            follower_count=profile.follower_count,
            is_following=profile.is_following,
            is_followed_by=profile.is_followed_by,
            is_blocked=profile.is_blocked,
            is_blocked_by=profile.is_blocked_by,
            is_subscribed=profile.is_subscribed,
            is_subscribed_by=profile.is_subscribed_by,
            subject_user_ref=subject_ref,
        )

    def _snapshot_profile(
        self,
        player_id: int,
        viewer_user_id: int,
        st: SnsPageSessionState,
        gen: int,
    ) -> SnsVirtualPageSnapshotDto:
        target_uid = st.profile_target_user_id
        if target_uid is None:
            target_uid = viewer_user_id

        if target_uid == viewer_user_id:
            prof = self._user_query.show_my_profile(viewer_user_id)
        else:
            prof = self._user_query.show_other_user_profile(target_uid, viewer_user_id)

        header = self._profile_header_from_dto(player_id, prof, viewer_user_id=viewer_user_id)

        lim = st.limit + 1
        raw = self._post_query.get_user_timeline(
            target_uid, viewer_user_id, limit=lim, offset=st.offset
        )
        posts, has_more = _slice_page(raw, st.limit)
        lines = [self._post_line(player_id, p) for p in posts]

        body = SnsProfileSnapshotDto(header=header, posts=lines)
        return SnsVirtualPageSnapshotDto(
            page_kind=SnsVirtualPageKind.PROFILE,
            snapshot_generation=gen,
            paging=self._paging(st, has_more),
            profile=body,
        )

    def _notification_line(
        self,
        player_id: int,
        n: NotificationDto,
    ) -> SnsNotificationLineSnapshotDto:
        nref = self._page_session.issue_notification_ref(player_id, n.notification_id)
        actor_ref: Optional[str] = None
        if n.actor_user_id:
            actor_ref = self._page_session.issue_user_ref(player_id, n.actor_user_id)
        post_ref: Optional[str] = None
        if n.related_post_id is not None:
            post_ref = self._page_session.issue_post_ref(player_id, n.related_post_id)
        reply_ref: Optional[str] = None
        if n.related_reply_id is not None:
            reply_ref = self._page_session.issue_reply_ref(player_id, n.related_reply_id)
        return SnsNotificationLineSnapshotDto(
            notification_type=n.notification_type,
            title=n.title,
            message=n.message,
            created_at=n.created_at,
            is_read=n.is_read,
            notification_ref=nref,
            actor_user_ref=actor_ref,
            related_post_ref=post_ref,
            related_reply_ref=reply_ref,
        )

    def _snapshot_notifications(
        self,
        player_id: int,
        viewer_user_id: int,
        st: SnsPageSessionState,
        gen: int,
    ) -> SnsVirtualPageSnapshotDto:
        lim = st.limit + 1
        raw = self._notification_query.get_user_notifications(
            viewer_user_id, limit=lim, offset=st.offset
        )
        rows, has_more = _slice_page(list(raw), st.limit)
        # 未読はリポジトリ集約の live query（別 projection 層は不要。Phase 6 確定）
        unread = self._notification_query.get_unread_count(viewer_user_id)
        lines = [self._notification_line(player_id, n) for n in rows]
        body = SnsNotificationsSnapshotDto(notifications=lines, unread_count=unread)
        return SnsVirtualPageSnapshotDto(
            page_kind=SnsVirtualPageKind.NOTIFICATIONS,
            snapshot_generation=gen,
            paging=self._paging(st, has_more),
            notifications=body,
        )


__all__ = ["SnsPageQueryService"]
