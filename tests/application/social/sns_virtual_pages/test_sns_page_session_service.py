"""SnsPageSessionService の単体テスト。"""

from ai_rpg_world.application.social.sns_virtual_pages import (
    SnsHomeTab,
    SnsPageSessionService,
    SnsSearchMode,
    SnsVirtualPageKind,
)


class TestSnsPageSessionService:
    def test_on_enter_sns_resets_to_home_following(self) -> None:
        svc = SnsPageSessionService()
        svc.set_page_kind(1, SnsVirtualPageKind.SEARCH)
        svc.set_search_context(1, mode=SnsSearchMode.KEYWORD, query="hello")
        svc.on_enter_sns(1)
        st = svc.get_state(1)
        assert st.page_kind == SnsVirtualPageKind.HOME
        assert st.home_tab == SnsHomeTab.FOLLOWING
        assert st.search_query == ""

    def test_on_exit_sns_drops_state(self) -> None:
        svc = SnsPageSessionService()
        svc.on_enter_sns(1)
        svc.set_page_kind(1, SnsVirtualPageKind.PROFILE)
        svc.on_exit_sns(1)
        st = svc.get_state(1)
        assert st.page_kind == SnsVirtualPageKind.HOME

    def test_issue_and_resolve_post_ref(self) -> None:
        svc = SnsPageSessionService()
        ref = svc.issue_post_ref(1, 42)
        assert ref.startswith("r_post_")
        assert svc.resolve_post_ref(1, ref) == 42

    def test_bump_snapshot_generation_invalidates_refs(self) -> None:
        svc = SnsPageSessionService()
        ref = svc.issue_post_ref(1, 7)
        assert svc.resolve_post_ref(1, ref) == 7
        svc.bump_snapshot_generation(1)
        assert svc.resolve_post_ref(1, ref) is None
        st = svc.get_state(1)
        assert st.snapshot_generation == 1

    def test_clamp_page_limit(self) -> None:
        svc = SnsPageSessionService()
        svc.set_paging(1, limit=500, offset=0)
        assert svc.get_state(1).limit == 100
        svc.set_paging(1, limit=0, offset=0)
        assert svc.get_state(1).limit == 1

    def test_resolve_user_reply_notification_refs(self) -> None:
        svc = SnsPageSessionService()
        ur = svc.issue_user_ref(1, 10)
        rr = svc.issue_reply_ref(1, 20)
        nr = svc.issue_notification_ref(1, 30)
        assert svc.resolve_user_ref(1, ur) == 10
        assert svc.resolve_reply_ref(1, rr) == 20
        assert svc.resolve_notification_ref(1, nr) == 30

    def test_unknown_ref_returns_none(self) -> None:
        svc = SnsPageSessionService()
        assert svc.resolve_post_ref(1, "r_post_99") is None
