import pytest
from unittest.mock import MagicMock
from typing import Set, Optional
from src.domain.sns.aggregate import ReplyAggregate
from src.domain.sns.value_object import PostContent, PostId, ReplyId, UserId, Like, Mention
from src.domain.sns.exception import (
    InvalidParentReferenceException,
    OwnershipException,
    InvalidContentTypeException,
    ContentTypeException,
    PostIdValidationException,
    ReplyIdValidationException,
    UserIdValidationException,
    ContentLengthValidationException,
    HashtagCountValidationException,
    MentionValidationException
)


class TestReplyAggregate:
    """ReplyAggregateの包括的なテストスイート"""

    def test_constructor_with_parent_post_success(self):
        """親ポストID付きでReplyAggregateを正常に作成"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        likes = set()
        mentions = set()

        reply = ReplyAggregate(reply_id, parent_post_id, None, author_user_id, content, likes, mentions)

        assert reply.content_id == reply_id
        assert reply.author_user_id == author_user_id
        assert reply.content == content
        assert reply.likes == likes
        assert reply.mentions == mentions
        assert reply.deleted is False
        assert reply.parent_post_id == parent_post_id
        assert reply.parent_reply_id is None

    def test_constructor_with_parent_reply_success(self):
        """親リプライID付きでReplyAggregateを正常に作成"""
        reply_id = ReplyId(1)
        parent_reply_id = ReplyId(2)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        likes = set()
        mentions = set()

        reply = ReplyAggregate(reply_id, None, parent_reply_id, author_user_id, content, likes, mentions)

        assert reply.content_id == reply_id
        assert reply.author_user_id == author_user_id
        assert reply.content == content
        assert reply.likes == likes
        assert reply.mentions == mentions
        assert reply.deleted is False
        assert reply.parent_post_id is None
        assert reply.parent_reply_id == parent_reply_id

    def test_constructor_without_parent_raises_error(self):
        """親参照なしでのコンストラクタが例外を発生させる"""
        reply_id = ReplyId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")

        with pytest.raises(InvalidParentReferenceException, match="リプライは親ポストまたは親リプライのどちらかを持つ必要があります"):
            ReplyAggregate(reply_id, None, None, author_user_id, content, set(), set())

    def test_constructor_with_both_parents_raises_error(self):
        """親ポストIDと親リプライIDの両方を指定すると例外が発生"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        parent_reply_id = ReplyId(2)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")

        with pytest.raises(InvalidParentReferenceException):
            ReplyAggregate(reply_id, parent_post_id, parent_reply_id, author_user_id, content, set(), set())

    def test_constructor_with_invalid_reply_id_raises_error(self):
        """無効なReplyIdでのコンストラクタが例外を発生"""
        with pytest.raises(ReplyIdValidationException):
            ReplyAggregate(ReplyId(0), PostId(1), None, UserId(1), PostContent("テスト"), set(), set())

    def test_constructor_with_invalid_post_id_raises_error(self):
        """無効なPostIdでのコンストラクタが例外を発生"""
        with pytest.raises(PostIdValidationException):
            ReplyAggregate(ReplyId(1), PostId(0), None, UserId(1), PostContent("テスト"), set(), set())

    def test_constructor_with_invalid_user_id_raises_error(self):
        """無効なUserIdでのコンストラクタが例外を発生"""
        with pytest.raises(UserIdValidationException):
            ReplyAggregate(ReplyId(1), PostId(1), None, UserId(0), PostContent("テスト"), set(), set())

    def test_create_with_parent_post_success(self):
        """create()メソッドで親ポストID付きリプライを正常に作成"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("@user1 @user2 テスト返信")

        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        assert reply.content_id == reply_id
        assert reply.author_user_id == author_user_id
        assert reply.content == content
        assert reply.deleted is False
        assert reply.parent_post_id == parent_post_id
        assert reply.parent_reply_id is None

        # メンションが自動的に作成されていることを確認
        mentioned_users = reply.get_mentioned_users()
        assert "user1" in mentioned_users
        assert "user2" in mentioned_users
        assert len(mentioned_users) == 2

    def test_create_with_parent_reply_success(self):
        """create()メソッドで親リプライID付きリプライを正常に作成"""
        reply_id = ReplyId(1)
        parent_reply_id = ReplyId(2)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")

        reply = ReplyAggregate.create(reply_id, None, parent_reply_id, author_user_id, content)

        assert reply.content_id == reply_id
        assert reply.author_user_id == author_user_id
        assert reply.content == content
        assert reply.deleted is False
        assert reply.parent_post_id is None
        assert reply.parent_reply_id == parent_reply_id

    def test_create_from_db_method(self):
        """create_from_db()メソッドのテスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        likes = {Like(UserId(2), PostId(1))}
        mentions = {Mention("user1", PostId(1))}
        deleted = False

        reply = ReplyAggregate.create_from_db(
            reply_id, parent_post_id, None, author_user_id, content, likes, mentions, deleted
        )

        assert reply.content_id == reply_id
        assert reply.author_user_id == author_user_id
        assert reply.content == content
        assert reply.likes == likes
        assert reply.mentions == mentions
        assert reply.deleted == deleted
        assert reply.parent_post_id == parent_post_id
        assert reply.parent_reply_id is None

    def test_reply_specific_properties(self):
        """ReplyAggregateの固有プロパティテスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        # ReplyAggregate固有のプロパティ
        assert reply.reply_id == reply_id
        assert reply.content_id == reply_id  # content_idもReplyIdを返す
        assert reply.get_content_type() == "reply"
        assert reply.get_parent_info() == (parent_post_id, None)

    def test_get_parent_info_with_parent_reply(self):
        """親リプライID付きの場合のget_parent_info()テスト"""
        reply_id = ReplyId(1)
        parent_reply_id = ReplyId(2)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        reply = ReplyAggregate.create(reply_id, None, parent_reply_id, author_user_id, content)

        assert reply.get_parent_info() == (None, parent_reply_id)

    def test_like_reply_functionality(self):
        """リプライへのいいね機能テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        user_id = UserId(2)

        # 初回いいね
        reply.like_reply(user_id)
        assert reply.is_liked_by_user(user_id) is True
        assert len(reply.likes) == 1

        # 同じユーザーがいいね解除
        reply.like_reply(user_id)
        assert reply.is_liked_by_user(user_id) is False
        assert len(reply.likes) == 0

    def test_like_reply_multiple_users(self):
        """複数ユーザーのリプライいいね機能テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        user1_id = UserId(2)
        user2_id = UserId(3)
        user3_id = UserId(4)

        # 複数のユーザーがいいね
        reply.like_reply(user1_id)
        reply.like_reply(user2_id)
        reply.like_reply(user3_id)

        assert reply.is_liked_by_user(user1_id) is True
        assert reply.is_liked_by_user(user2_id) is True
        assert reply.is_liked_by_user(user3_id) is True
        assert len(reply.likes) == 3

        # 一部のユーザーがいいね解除
        reply.like_reply(user2_id)
        assert reply.is_liked_by_user(user2_id) is False
        assert len(reply.likes) == 2

    def test_delete_reply_by_owner(self):
        """リプライ作成者による削除テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        reply.delete_reply(author_user_id)
        assert reply.deleted is True

    def test_delete_reply_by_non_owner_raises_error(self):
        """他人によるリプライ削除が拒否されるテスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        other_user_id = UserId(2)

        with pytest.raises(OwnershipException):
            reply.delete_reply(other_user_id)

    def test_mention_extraction_from_content(self):
        """コンテンツからのメンション抽出テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("@user1 @user2 こんにちは！ #test")

        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        mentioned_users = reply.get_mentioned_users()
        assert "user1" in mentioned_users
        assert "user2" in mentioned_users
        assert len(mentioned_users) == 2

    def test_mention_with_no_mentions(self):
        """メンションなしのコンテンツテスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("メンションなしの返信")

        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        mentioned_users = reply.get_mentioned_users()
        assert len(mentioned_users) == 0

    def test_mention_with_special_characters(self):
        """特殊文字を含むメンションのテスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("@user_name @user-name @user.name テスト")

        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        mentioned_users = reply.get_mentioned_users()
        assert "user_name" in mentioned_users
        assert "user-name" in mentioned_users
        assert "user.name" in mentioned_users
        assert len(mentioned_users) == 3

    def test_content_validation_max_length(self):
        """最大文字数でのコンテンツ作成テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)

        # 最大文字数（280文字）のコンテンツ
        long_content = "あ" * 280
        content = PostContent(long_content)

        # 最大文字数では成功するはず
        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)
        assert reply.content.content == long_content

    def test_content_validation_over_max_length(self):
        """最大文字数を超えるコンテンツで例外が発生"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)

        # 最大文字数を超えるコンテンツ
        long_content = "あ" * 281

        with pytest.raises(ContentLengthValidationException):
            PostContent(long_content)

    def test_content_validation_max_hashtags(self):
        """最大ハッシュタグ数でのコンテンツ作成テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)

        # 最大ハッシュタグ数（10個）
        hashtags = tuple(f"tag{i}" for i in range(10))
        content = PostContent("テスト", hashtags=hashtags)

        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)
        assert reply.content.hashtags == hashtags

    def test_content_validation_over_max_hashtags(self):
        """最大ハッシュタグ数を超えるコンテンツで例外が発生"""
        # 最大ハッシュタグ数を超える
        hashtags = tuple(f"tag{i}" for i in range(11))

        with pytest.raises(HashtagCountValidationException):
            PostContent("テスト", hashtags=hashtags)

    def test_parent_info_with_both_none_should_never_happen(self):
        """親情報が両方Noneになるケースは発生しないことを確認"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")

        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        # 親情報は必ずどちらか一方が設定されている
        parent_post, parent_reply = reply.get_parent_info()
        assert (parent_post is not None) or (parent_reply is not None)

    def test_event_emission_on_creation(self):
        """作成時のイベント発行テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("@user1 テスト返信")

        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        # イベントが発行されていることを確認
        events = reply.get_events()
        assert len(events) >= 2  # SnsContentCreatedEvent + SnsContentMentionedEvent

        # 作成イベントの確認
        created_event = events[0]
        assert created_event.aggregate_id == reply_id
        assert created_event.aggregate_type == "ReplyAggregate"
        assert created_event.content_type == "reply"

    def test_like_event_emission(self):
        """いいね時のイベント発行テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        user_id = UserId(2)
        reply.like_reply(user_id)

        # いいねイベントが発行されていることを確認
        events = reply.get_events()
        like_events = [e for e in events if hasattr(e, 'content_type') and e.content_type == "reply"]
        assert len(like_events) > 0

    def test_delete_event_emission(self):
        """削除時のイベント発行テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト返信")
        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        reply.delete_reply(author_user_id)

        # 削除イベントが発行されていることを確認
        events = reply.get_events()
        delete_events = [e for e in events if hasattr(e, 'content_type') and e.content_type == "reply"]
        assert len(delete_events) > 0

    def test_mention_event_emission(self):
        """メンション時のイベント発行テスト"""
        reply_id = ReplyId(1)
        parent_post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("@user1 テスト返信")

        reply = ReplyAggregate.create(reply_id, parent_post_id, None, author_user_id, content)

        # メンションイベントが発行されていることを確認
        events = reply.get_events()
        mention_events = [e for e in events if hasattr(e, 'mentioned_user_names')]
        assert len(mention_events) > 0
        assert "user1" in mention_events[0].mentioned_user_names
