"""SnsPageQueryService: 画面スナップショットと ref の単体テスト（query をモック）。"""

from datetime import datetime
from unittest.mock import MagicMock

from ai_rpg_world.application.social.contracts.dtos import (
    NotificationDto,
    PostDto,
    ReplyDto,
    ReplyThreadDto,
    UserProfileDto,
)
from ai_rpg_world.application.social.sns_virtual_pages import (
    SnsHomeTab,
    SnsPageQueryService,
    SnsPageSessionService,
    SnsSearchMode,
    SnsVirtualPageKind,
)
def _post(pid: int, aid: int, content: str) -> PostDto:
    return PostDto(
        post_id=pid,
        author_user_id=aid,
        author_user_name="u",
        author_display_name="Author",
        content=content,
        hashtags=[],
        visibility="public",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        like_count=3,
        reply_count=1,
        is_liked_by_viewer=True,
        is_replied_by_viewer=False,
        mentioned_users=[],
        is_deleted=False,
    )


class TestSnsPageQueryService:
    def test_home_following_issues_refs_without_raw_ids_in_snapshot(self) -> None:
        session = SnsPageSessionService()
        pq = MagicMock()
        pq.get_home_timeline.return_value = [_post(10, 20, "hello world")]
        rq = MagicMock()
        nq = MagicMock()
        uq = MagicMock()
        svc = SnsPageQueryService(pq, rq, nq, uq, session)
        session.on_enter_sns(1)
        st = session.get_state(1)
        st.page_kind = SnsVirtualPageKind.HOME
        st.home_tab = SnsHomeTab.FOLLOWING
        snap = svc.get_current_page_snapshot(1, viewer_user_id=1)
        assert snap.page_kind == SnsVirtualPageKind.HOME
        assert snap.home is not None
        assert len(snap.home.posts) == 1
        row = snap.home.posts[0]
        assert row.post_ref.startswith("r_post_")
        assert row.author_user_ref is not None and row.author_user_ref.startswith("r_user_")
        pq.get_home_timeline.assert_called_once()
        assert session.resolve_post_ref(1, row.post_ref) == 10
        assert session.resolve_user_ref(1, row.author_user_ref) == 20

    def test_home_popular_includes_trending_hashtags(self) -> None:
        session = SnsPageSessionService()
        pq = MagicMock()
        pq.get_popular_posts.return_value = [_post(1, 2, "p")]
        pq.get_trending_hashtags.return_value = ["#a"]
        svc = SnsPageQueryService(pq, MagicMock(), MagicMock(), MagicMock(), session)
        session.on_enter_sns(1)
        st = session.get_state(1)
        st.home_tab = SnsHomeTab.POPULAR
        snap = svc.get_current_page_snapshot(1, 1)
        assert snap.home is not None
        assert snap.home.trending_hashtags == ["#a"]

    def test_has_more_when_extra_row(self) -> None:
        session = SnsPageSessionService()
        pq = MagicMock()
        pq.get_home_timeline.return_value = [_post(i, 1, str(i)) for i in range(21)]
        svc = SnsPageQueryService(pq, MagicMock(), MagicMock(), MagicMock(), session)
        session.on_enter_sns(1)
        st = session.get_state(1)
        st.limit = 20
        snap = svc.get_current_page_snapshot(1, 1)
        assert snap.paging.has_more is True
        assert snap.home is not None
        assert len(snap.home.posts) == 20

    def test_post_detail_maps_replies(self) -> None:
        session = SnsPageSessionService()
        root = _post(100, 5, "root")
        rep = ReplyDto(
            reply_id=200,
            parent_post_id=100,
            parent_reply_id=None,
            author_user_id=6,
            author_user_name="x",
            author_display_name="Rep",
            content="reply text",
            hashtags=[],
            visibility="public",
            created_at=datetime(2026, 1, 2, 0, 0, 0),
            like_count=0,
            is_liked_by_viewer=False,
            mentioned_users=[],
            is_deleted=False,
            depth=1,
            has_replies=False,
            reply_count=0,
        )
        rq = MagicMock()
        rq.get_reply_thread.return_value = ReplyThreadDto(post=root, replies=[rep])
        svc = SnsPageQueryService(MagicMock(), rq, MagicMock(), MagicMock(), session)
        session.on_enter_sns(1)
        st = session.get_state(1)
        st.page_kind = SnsVirtualPageKind.POST_DETAIL
        st.post_detail_root_post_id = 100
        snap = svc.get_current_page_snapshot(1, 1)
        assert snap.post_detail is not None
        assert snap.post_detail.root_post.post_ref.startswith("r_post_")
        assert len(snap.post_detail.replies) == 1
        rr = snap.post_detail.replies[0]
        assert rr.reply_ref.startswith("r_reply_")
        assert session.resolve_reply_ref(1, rr.reply_ref) == 200

    def test_post_detail_missing_root_returns_error(self) -> None:
        session = SnsPageSessionService()
        svc = SnsPageQueryService(MagicMock(), MagicMock(), MagicMock(), MagicMock(), session)
        session.on_enter_sns(1)
        st = session.get_state(1)
        st.page_kind = SnsVirtualPageKind.POST_DETAIL
        st.post_detail_root_post_id = None
        snap = svc.get_current_page_snapshot(1, 1)
        assert snap.error is not None
        assert snap.post_detail is None

    def test_search_keyword(self) -> None:
        session = SnsPageSessionService()
        pq = MagicMock()
        pq.search_posts_by_keyword.return_value = [_post(1, 1, "x")]
        svc = SnsPageQueryService(pq, MagicMock(), MagicMock(), MagicMock(), session)
        session.on_enter_sns(1)
        st = session.get_state(1)
        st.page_kind = SnsVirtualPageKind.SEARCH
        st.search_mode = SnsSearchMode.KEYWORD
        st.search_query = "hello"
        snap = svc.get_current_page_snapshot(1, 1)
        assert snap.search is not None
        assert snap.search.search_query == "hello"
        pq.search_posts_by_keyword.assert_called_once()

    def test_profile_self(self) -> None:
        session = SnsPageSessionService()
        prof = UserProfileDto(
            user_id=1,
            user_name="me",
            display_name="Me",
            bio="bio",
            is_following=None,
            is_followed_by=None,
            is_blocked=None,
            is_blocked_by=None,
            is_subscribed=None,
            is_subscribed_by=None,
            followee_count=1,
            follower_count=2,
        )
        uq = MagicMock()
        uq.show_my_profile.return_value = prof
        pq = MagicMock()
        pq.get_user_timeline.return_value = []
        svc = SnsPageQueryService(pq, MagicMock(), MagicMock(), uq, session)
        session.on_enter_sns(1)
        st = session.get_state(1)
        st.page_kind = SnsVirtualPageKind.PROFILE
        st.profile_target_user_id = None
        snap = svc.get_current_page_snapshot(1, viewer_user_id=1)
        assert snap.profile is not None
        assert snap.profile.header.is_self is True
        assert snap.profile.header.subject_user_ref is None
        uq.show_my_profile.assert_called_once_with(1)

    def test_notifications_unread_and_refs(self) -> None:
        session = SnsPageSessionService()
        n = NotificationDto(
            notification_id=50,
            user_id=1,
            notification_type="like",
            title="t",
            message="m",
            actor_user_id=2,
            actor_user_name="a",
            created_at=datetime(2026, 1, 1, 0, 0, 0),
            is_read=False,
            related_post_id=10,
            related_reply_id=None,
        )
        nq = MagicMock()
        nq.get_user_notifications.return_value = [n]
        nq.get_unread_count.return_value = 3
        svc = SnsPageQueryService(MagicMock(), MagicMock(), nq, MagicMock(), session)
        session.on_enter_sns(1)
        st = session.get_state(1)
        st.page_kind = SnsVirtualPageKind.NOTIFICATIONS
        snap = svc.get_current_page_snapshot(1, 1)
        assert snap.notifications is not None
        assert snap.notifications.unread_count == 3
        line = snap.notifications.notifications[0]
        assert line.notification_ref.startswith("r_notif_")
        assert session.resolve_notification_ref(1, line.notification_ref) == 50
        assert line.related_post_ref is not None
        assert session.resolve_post_ref(1, line.related_post_ref) == 10

    def test_snapshot_bumps_generation_each_call(self) -> None:
        session = SnsPageSessionService()
        pq = MagicMock()
        pq.get_home_timeline.return_value = []
        svc = SnsPageQueryService(pq, MagicMock(), MagicMock(), MagicMock(), session)
        session.on_enter_sns(1)
        s1 = svc.get_current_page_snapshot(1, 1).snapshot_generation
        s2 = svc.get_current_page_snapshot(1, 1).snapshot_generation
        assert s2 > s1
