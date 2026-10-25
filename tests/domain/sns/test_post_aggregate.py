"""投稿に固有の親禁止・公開範囲・並び順・表示と子返信管理を守る。"""

from datetime import datetime

import pytest

from ai_rpg_world.domain.sns.aggregate import PostAggregate
from ai_rpg_world.domain.sns.enum import PostVisibility
from ai_rpg_world.domain.sns.exception import InvalidParentReferenceException
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId

SAVED_AT = datetime(2020, 2, 3, 4, 5, 6)


class TestPostAggregate:
    """投稿は親を持たず、子返信IDの追加・除去は他の返信を壊さない。"""

    def test_constructor_with_parent_references_raises_error(self):
        """親参照を含むコンストラクタが例外を発生させるテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        parent_post_id = PostId(2)

        with pytest.raises(
            InvalidParentReferenceException, match="ポストは親ポストまたは親リプライを持つことはできません"
        ):
            PostAggregate(post_id, author_user_id, content, set(), set(), set(), False, parent_post_id)

    def test_reply_ids_management(self):
        """リプライID管理機能のテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        # 初期状態：リプライなし
        assert len(post.reply_ids) == 0
        assert post.get_reply_count() == 0

        # リプライ追加
        from ai_rpg_world.domain.sns.value_object import ReplyId

        reply_id1 = ReplyId(1)
        reply_id2 = ReplyId(2)

        post.add_reply(reply_id1)
        assert len(post.reply_ids) == 1
        assert reply_id1 in post.reply_ids
        assert post.get_reply_count() == 1

        post.add_reply(reply_id2)
        assert len(post.reply_ids) == 2
        assert reply_id1 in post.reply_ids
        assert reply_id2 in post.reply_ids
        assert post.get_reply_count() == 2

        # 同じリプライを追加しても変化なし
        post.add_reply(reply_id1)
        assert len(post.reply_ids) == 2
        assert post.get_reply_count() == 2

        # リプライ削除
        post.remove_reply(reply_id1)
        assert len(post.reply_ids) == 1
        assert reply_id1 not in post.reply_ids
        assert reply_id2 in post.reply_ids
        assert post.get_reply_count() == 1

        # 存在しないリプライを削除しても変化なし
        post.remove_reply(ReplyId(999))
        assert len(post.reply_ids) == 1
        assert post.get_reply_count() == 1


def test_is_private():
    """元の3公開範囲では、作者限定の投稿だけがis_private=Trueになる。"""
    cases = [
        (1, "プライベート投稿", PostVisibility.PRIVATE, True),
        (2, "パブリック投稿", PostVisibility.PUBLIC, False),
        (3, "フォロワー限定投稿", PostVisibility.FOLLOWERS_ONLY, False),
    ]
    for number, body, visibility, expected in cases:
        post = PostAggregate.create(PostId(number), UserId(1), PostContent.create(body, visibility))
        assert post.is_private() is expected


def test_created_at_sort_key():
    """新規投稿も保存時刻付き復元もdatetimeの作成日時を並び順に使い、現在時刻へ置き換えない。"""
    post = PostAggregate.create(PostId(1), UserId(1), PostContent("テスト投稿"))
    assert isinstance(post.get_sort_key_by_created_at(), datetime)
    assert post.get_sort_key_by_created_at() == post.created_at
    restored = PostAggregate.create_from_db(
        PostId(1), UserId(1), PostContent("テスト投稿"), set(), set(), set(), created_at=SAVED_AT
    )
    assert restored.get_sort_key_by_created_at() == SAVED_AT


def test_get_display_info_preserves_saved_fields():
    """元の11表示キーを保ち、閲覧者のいいね・削除後・保存時刻も状態から投影する。"""
    content = PostContent("テスト投稿", hashtags=("#test",), visibility=PostVisibility.PUBLIC)
    post = PostAggregate.create(PostId(1), UserId(1), content)
    post.like_post(UserId(2))
    post.add_reply(ReplyId(1))
    post.add_reply(ReplyId(2))
    expected = {
        "post_id": 1,
        "author_user_id": 1,
        "content": "テスト投稿",
        "hashtags": ["#test"],
        "visibility": "public",
        "like_count": 1,
        "reply_count": 2,
        "is_liked_by_viewer": False,
        "is_replied_by_viewer": False,
        "mentioned_users": [],
        "is_deleted": False,
    }
    displayed = post.get_display_info(UserId(3))
    assert {key: displayed[key] for key in expected} == expected
    assert post.get_display_info(UserId(2))["is_liked_by_viewer"] is True
    post.delete_post(UserId(1))
    assert post.get_display_info(UserId(3))["is_deleted"] is True
    restored = PostAggregate.create_from_db(PostId(1), UserId(1), content, set(), set(), set(), created_at=SAVED_AT)
    assert restored.get_display_info(UserId(3))["created_at"] == SAVED_AT
