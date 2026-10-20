"""返信の直接構築は、投稿親と返信親のどちらか一方だけを受け付ける。"""

import pytest

from ai_rpg_world.domain.sns.aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.exception import InvalidParentReferenceException
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, ReplyId, UserId


class TestReplyAggregate:
    """親がない返信と両方の親がある返信を、親参照専用の例外で拒否する。"""

    def test_constructor_without_parent_raises_error(self):
        """親参照なしでのコンストラクタが例外を発生させる"""
        reply_id = ReplyId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")

        with pytest.raises(InvalidParentReferenceException, match="リプライは親ポストまたは親リプライのどちらかを持つ必要があります"):
            ReplyAggregate(reply_id, author_user_id, content, set(), set(), set(), deleted=False, parent_post_id=None, parent_reply_id=None)

    def test_constructor_with_both_parents_raises_error(self):
        """親ポストIDと親リプライIDの両方を指定すると例外が発生"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        parent_reply_id = ReplyId(2)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")

        with pytest.raises(InvalidParentReferenceException):
            ReplyAggregate(reply_id, author_user_id, content, set(), set(), set(), deleted=False, parent_post_id=parent_post_id, parent_reply_id=parent_reply_id)
