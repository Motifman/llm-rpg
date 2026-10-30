"""返信が増えても投稿詳細の画面サイズと参照数がページ上限を超えないことを保証する。"""

from dataclasses import replace
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.social.contracts.dtos import PostDto, ReplyDto, ReplyThreadDto
from ai_rpg_world.application.social.sns_virtual_pages import (
    SnsPageQueryService,
    SnsPageSessionService,
    SnsVirtualPageKind,
)


def _thread(reply_count: int) -> ReplyThreadDto:
    root = PostDto(
        post_id=1,
        author_user_id=1,
        author_user_name="author",
        author_display_name="投稿者",
        content="連絡",
        hashtags=[],
        visibility="public",
        created_at=datetime(2026, 1, 1),
        like_count=0,
        reply_count=reply_count,
        is_liked_by_viewer=False,
        is_replied_by_viewer=False,
        mentioned_users=[],
        is_deleted=False,
    )
    reply = ReplyDto(
        reply_id=1,
        parent_post_id=1,
        parent_reply_id=None,
        author_user_id=2,
        author_user_name="replier",
        author_display_name="返信者",
        content="あ" * 280,
        hashtags=[],
        visibility="public",
        created_at=datetime(2026, 1, 1),
        like_count=0,
        is_liked_by_viewer=False,
        mentioned_users=[],
        is_deleted=False,
        depth=1,
        has_replies=False,
        reply_count=0,
    )
    return ReplyThreadDto(post=root, replies=[replace(reply, reply_id=i + 1) for i in range(reply_count)])


@pytest.mark.parametrize(
    ("reply_count", "offset", "expected_ids", "has_more"),
    [
        (0, 0, [], False),
        (3, 0, [1, 2, 3], False),
        (4, 0, [1, 2, 3], True),
        (7, 3, [4, 5, 6], True),
        (7, 6, [7], False),
        (7, 9, [], False),
    ],
)
def test_detail_honors_reply_page_and_issues_only_visible_refs(
    reply_count: int,
    offset: int,
    expected_ids: list[int],
    has_more: bool,
) -> None:
    """投稿詳細は offset から limit 件の返信だけを表示し、続きの有無を正しく返す。"""
    session = SnsPageSessionService()
    session.set_page_kind(1, SnsVirtualPageKind.POST_DETAIL)
    session.set_post_detail_root_post_id(1, 1)
    session.set_paging(1, limit=3, offset=offset)
    replies = MagicMock()
    replies.get_reply_thread.return_value = _thread(reply_count)
    query = SnsPageQueryService(MagicMock(), replies, MagicMock(), MagicMock(), session)

    snapshot = query.get_current_page_snapshot(1, viewer_user_id=1)

    assert snapshot.post_detail is not None
    assert [session.resolve_reply_ref(1, row.reply_ref) for row in snapshot.post_detail.replies] == expected_ids
    assert snapshot.paging.offset == offset
    assert snapshot.paging.limit == 3
    assert snapshot.paging.has_more is has_more
    assert len(session.get_state(1).ref_to_reply_id) == len(expected_ids)
    assert session.resolve_post_ref(1, snapshot.post_detail.root_post.post_ref) == 1


def test_detail_with_many_replies_keeps_only_one_page_and_invalidates_previous_refs() -> None:
    """千件の返信があっても一画面は三件に収まり、次ページでは前ページの参照が無効になる。"""
    session = SnsPageSessionService()
    session.set_page_kind(1, SnsVirtualPageKind.POST_DETAIL)
    session.set_post_detail_root_post_id(1, 1)
    session.set_paging(1, limit=3)
    replies = MagicMock()
    replies.get_reply_thread.return_value = _thread(1000)
    query = SnsPageQueryService(MagicMock(), replies, MagicMock(), MagicMock(), session)
    first = query.get_current_page_snapshot(1, viewer_user_id=1)
    assert first.post_detail is not None
    old_refs = [row.reply_ref for row in first.post_detail.replies]
    assert len(old_refs) == 3
    assert sum(len(row.content_preview) for row in first.post_detail.replies) <= 600

    session.set_paging(1, offset=3)
    second = query.get_current_page_snapshot(1, viewer_user_id=1)

    assert second.post_detail is not None
    assert [session.resolve_reply_ref(1, row.reply_ref) for row in second.post_detail.replies] == [4, 5, 6]
    assert all(session.resolve_reply_ref(1, ref) is None for ref in old_refs)
    assert len(session.get_state(1).ref_to_reply_id) == 3


def test_detail_preserves_thread_order_and_depth_across_page_boundary() -> None:
    """親子をまたぐページでも、返信の表示順と深さをID順へ並べ替えずに保持する。"""
    thread = _thread(4)
    thread = replace(
        thread,
        replies=[
            replace(thread.replies[0], reply_id=40, depth=1),
            replace(thread.replies[1], reply_id=3, parent_post_id=None, parent_reply_id=40, depth=2),
            replace(thread.replies[2], reply_id=91, parent_post_id=None, parent_reply_id=3, depth=3),
            replace(thread.replies[3], reply_id=2, depth=1),
        ],
    )
    session = SnsPageSessionService()
    session.set_page_kind(1, SnsVirtualPageKind.POST_DETAIL)
    session.set_post_detail_root_post_id(1, 1)
    session.set_paging(1, limit=2, offset=1)
    replies = MagicMock()
    replies.get_reply_thread.return_value = thread
    query = SnsPageQueryService(MagicMock(), replies, MagicMock(), MagicMock(), session)

    snapshot = query.get_current_page_snapshot(1, viewer_user_id=1)

    assert snapshot.post_detail is not None
    assert [session.resolve_reply_ref(1, row.reply_ref) for row in snapshot.post_detail.replies] == [3, 91]
    assert [row.depth for row in snapshot.post_detail.replies] == [2, 3]
    assert snapshot.paging.has_more is True
