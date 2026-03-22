"""SnsToolExecutor: 仮想 SNS 画面ナビゲーションツールの単体テスト。"""

import json
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.sns_executor import SnsToolExecutor
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SNS_FOLLOW,
    TOOL_NAME_SNS_LIKE_POST,
    TOOL_NAME_SNS_MARK_NOTIFICATION_READ,
    TOOL_NAME_SNS_OPEN_PAGE,
    TOOL_NAME_SNS_OPEN_REF,
    TOOL_NAME_SNS_VIEW_CURRENT_PAGE,
)
from ai_rpg_world.application.social.contracts.dtos import NotificationDto, ReplyDto
from ai_rpg_world.application.social.sns_virtual_pages import (
    SnsPageQueryService,
    SnsPageSessionService,
)
from ai_rpg_world.application.social.sns_virtual_pages.kinds import SnsVirtualPageKind


@pytest.fixture
def page_session() -> SnsPageSessionService:
    return SnsPageSessionService()


@pytest.fixture
def page_query(page_session: SnsPageSessionService) -> SnsPageQueryService:
    return SnsPageQueryService(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        page_session,
    )


def test_view_current_page_returns_json_snapshot(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_VIEW_CURRENT_PAGE]
    r = h(1, {})
    assert r.success
    data = json.loads(r.message or "{}")
    assert data["page_kind"] == "home"


def test_open_page_post_detail_requires_post_ref(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_OPEN_PAGE]
    r = h(1, {"page": "post_detail"})
    assert not r.success


def test_open_page_search(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_OPEN_PAGE]
    r = h(1, {"page": "search", "search_query": "test", "search_mode": "keyword"})
    assert r.success
    st = page_session.get_state(1)
    assert st.page_kind == SnsVirtualPageKind.SEARCH


def test_open_ref_user(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    page_session.issue_user_ref(1, 42)
    rmap = page_session.get_state(1).ref_to_user_id
    ref = next(iter(rmap.keys()))
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_OPEN_REF]
    res = h(1, {"ref": ref})
    assert res.success
    st = page_session.get_state(1)
    assert st.page_kind == SnsVirtualPageKind.PROFILE
    assert st.profile_target_user_id == 42


def test_open_ref_reply_uses_reply_query(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    page_session.issue_reply_ref(1, 99)
    rmap = page_session.get_state(1).ref_to_reply_id
    ref = next(iter(rmap.keys()))
    rq = MagicMock()
    rq.get_reply_by_id = MagicMock(
        return_value=ReplyDto(
            reply_id=99,
            parent_post_id=7,
            parent_reply_id=None,
            author_user_id=1,
            author_user_name="u",
            author_display_name="U",
            content="x",
            hashtags=[],
            visibility="public",
            created_at=__import__("datetime").datetime.now(),
            like_count=0,
            is_liked_by_viewer=False,
            mentioned_users=[],
            is_deleted=False,
            depth=0,
        )
    )
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
        reply_query_service=rq,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_OPEN_REF]
    res = h(1, {"ref": ref})
    assert res.success
    st = page_session.get_state(1)
    assert st.post_detail_root_post_id == 7


def test_switch_tab_only_on_home(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SNS_SWITCH_TAB

    page_session.set_page_kind(1, SnsVirtualPageKind.SEARCH)
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_SWITCH_TAB]
    r = h(1, {"tab": "popular"})
    assert not r.success


def test_open_ref_notification_resolves_post(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    from datetime import datetime

    from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SNS_OPEN_REF

    page_session.issue_notification_ref(1, 55)
    rmap = page_session.get_state(1).ref_to_notification_id
    ref = next(iter(rmap.keys()))
    nq = MagicMock()
    nq.get_user_notifications = MagicMock(
        return_value=[
            NotificationDto(
                notification_id=55,
                user_id=1,
                notification_type="like",
                title="t",
                message="m",
                actor_user_id=2,
                actor_user_name="a",
                created_at=datetime.now(),
                is_read=False,
                related_post_id=100,
            )
        ]
    )
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
        notification_query_service=nq,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_OPEN_REF]
    res = h(1, {"ref": ref})
    assert res.success
    st = page_session.get_state(1)
    assert st.post_detail_root_post_id == 100


def test_like_post_resolves_post_ref(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    page_session.issue_post_ref(1, 77)
    ref = next(iter(page_session.get_state(1).ref_to_post_id.keys()))
    post_service = MagicMock()
    post_service.like_post.return_value = MagicMock(success=True, message="ok")
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
        post_service=post_service,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_LIKE_POST]
    res = h(1, {"post_ref": ref})
    assert res.success
    cmd = post_service.like_post.call_args[0][0]
    assert cmd.post_id == 77


def test_follow_uses_current_profile_target_when_ref_omitted(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    page_session.set_page_kind(1, SnsVirtualPageKind.PROFILE)
    page_session.set_profile_target_user_id(1, 42)
    user_command_service = MagicMock()
    user_command_service.follow_user.return_value = MagicMock(success=True, message="ok")
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
        user_command_service=user_command_service,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_FOLLOW]
    res = h(1, {})
    assert res.success
    cmd = user_command_service.follow_user.call_args[0][0]
    assert cmd.followee_user_id == 42


def test_mark_notification_read_resolves_notification_ref(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    page_session.issue_notification_ref(1, 55)
    ref = next(iter(page_session.get_state(1).ref_to_notification_id.keys()))
    notification_command_service = MagicMock()
    notification_command_service.mark_notification_as_read.return_value = MagicMock(
        success=True, message="ok"
    )
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
        notification_command_service=notification_command_service,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_MARK_NOTIFICATION_READ]
    res = h(1, {"notification_ref": ref})
    assert res.success
    cmd = notification_command_service.mark_notification_as_read.call_args[0][0]
    assert cmd.notification_id == 55


def test_open_ref_notification_without_targets_returns_failure(
    page_session: SnsPageSessionService,
    page_query: SnsPageQueryService,
) -> None:
    from datetime import datetime

    page_session.issue_notification_ref(1, 56)
    ref = next(iter(page_session.get_state(1).ref_to_notification_id.keys()))
    nq = MagicMock()
    nq.get_user_notifications = MagicMock(
        return_value=[
            NotificationDto(
                notification_id=56,
                user_id=1,
                notification_type="system",
                title="t",
                message="m",
                actor_user_id=None,
                actor_user_name=None,
                created_at=datetime.now(),
                is_read=False,
                related_post_id=None,
                related_reply_id=None,
            )
        ]
    )
    ex = SnsToolExecutor(
        sns_page_session=page_session,
        sns_page_query_service=page_query,
        notification_query_service=nq,
    )
    h = ex.get_handlers()[TOOL_NAME_SNS_OPEN_REF]
    res = h(1, {"ref": ref})
    assert not res.success
    assert "遷移" in (res.message or "")
