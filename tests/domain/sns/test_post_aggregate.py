import pytest
from unittest.mock import MagicMock
from typing import Set
from ai_rpg_world.domain.sns.aggregate import PostAggregate
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, UserId, Like, Mention
from ai_rpg_world.domain.sns.enum import PostVisibility
from ai_rpg_world.domain.sns.exception import (
    InvalidContentTypeException,
    InvalidParentReferenceException,
    OwnershipException,
    ContentLengthValidationException,
    HashtagCountValidationException,
    VisibilityValidationException,
    PostIdValidationException,
    UserIdValidationException
)


class TestPostAggregate:
    """PostAggregateの包括的なテストスイート"""

    def test_constructor_success(self):
        """正常なPostAggregateのコンストラクタテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        likes = set()
        mentions = set()

        post = PostAggregate(post_id, author_user_id, content, likes, mentions, set())

        assert post.content_id == post_id
        assert post.author_user_id == author_user_id
        assert post.content == content
        assert post.likes == likes
        assert post.mentions == mentions
        assert post.deleted is False
        assert post.parent_post_id is None
        assert post.parent_reply_id is None

    def test_constructor_with_parent_references_raises_error(self):
        """親参照を含むコンストラクタが例外を発生させるテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        parent_post_id = PostId(2)

        with pytest.raises(InvalidParentReferenceException, match="ポストは親ポストまたは親リプライを持つことはできません"):
            PostAggregate(post_id, author_user_id, content, set(), set(), set(), False, parent_post_id)

    def test_create_method_success(self):
        """create()メソッドの正常動作テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("@user1 @user2 テスト投稿")

        post = PostAggregate.create(post_id, author_user_id, content)

        assert post.content_id == post_id
        assert post.author_user_id == author_user_id
        assert post.content == content
        assert post.deleted is False
        assert post.parent_post_id is None
        assert post.parent_reply_id is None

        # メンションが自動的に作成されていることを確認
        mentioned_users = post.get_mentioned_users()
        assert "user1" in mentioned_users
        assert "user2" in mentioned_users
        assert len(mentioned_users) == 2

    def test_create_from_db_method(self):
        """create_from_db()メソッドのテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        likes = {Like(UserId(2), post_id)}
        mentions = {Mention("user1", post_id)}
        deleted = False

        reply_ids = set()  # テスト用の空のreply_ids
        post = PostAggregate.create_from_db(
            post_id, author_user_id, content, likes, mentions, reply_ids, deleted
        )

        assert post.content_id == post_id
        assert post.author_user_id == author_user_id
        assert post.content == content
        assert post.likes == likes
        assert post.mentions == mentions
        assert post.deleted == deleted

    def test_properties(self):
        """PostAggregateのプロパティテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        # PostAggregate固有のプロパティ
        assert post.post_id == post_id
        assert post.post_content == content

        # 基底クラスのプロパティ
        assert post.content_id == post_id
        assert post.author_user_id == author_user_id
        assert post.content == content
        assert post.likes == set()
        assert post.mentions == set()
        assert post.deleted is False
        assert post.parent_post_id is None
        assert post.parent_reply_id is None

    def test_get_content_type(self):
        """get_content_type()メソッドのテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        assert post.get_content_type() == "post"

    def test_get_parent_info(self):
        """get_parent_info()メソッドのテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        parent_post_id, parent_reply_id = post.get_parent_info()
        assert parent_post_id is None
        assert parent_reply_id is None

    def test_mentioned_users(self):
        """mentioned_users()メソッドのテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("@user1 @user2 テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        mentioned_users = post.mentioned_users()
        assert mentioned_users == {"user1", "user2"}

    def test_like_post_functionality(self):
        """like_post()メソッドのテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        user_id = UserId(2)

        # 初回いいね
        post.like_post(user_id)
        assert post.is_liked_by_user(user_id) is True
        assert len(post.likes) == 1

        # 2回目の実行でいいね解除
        post.like_post(user_id)
        assert post.is_liked_by_user(user_id) is False
        assert len(post.likes) == 0

    def test_like_post_multiple_users(self):
        """複数ユーザーによるいいね機能テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        user1_id = UserId(2)
        user2_id = UserId(3)
        user3_id = UserId(4)

        # 複数のユーザーがいいね
        post.like_post(user1_id)
        post.like_post(user2_id)
        post.like_post(user3_id)

        assert post.is_liked_by_user(user1_id) is True
        assert post.is_liked_by_user(user2_id) is True
        assert post.is_liked_by_user(user3_id) is True
        assert len(post.likes) == 3

        # 一部のユーザーがいいね解除
        post.like_post(user2_id)
        assert post.is_liked_by_user(user2_id) is False
        assert len(post.likes) == 2

    def test_delete_post_functionality(self):
        """delete_post()メソッドのテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        # 作成者が削除
        post.delete_post(author_user_id)
        assert post.deleted is True

    def test_delete_post_unauthorized_user_raises_error(self):
        """未許可ユーザーによる削除エラーテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        unauthorized_user_id = UserId(2)

        with pytest.raises(OwnershipException, match="ユーザーはこのpostを削除する権限がありません"):
            post.delete_post(unauthorized_user_id)

    def test_create_mentions_from_content_static(self):
        """_create_mentions_from_content_static()メソッドのテスト"""
        post_id = PostId(1)
        content = PostContent("@user1 @user2 テスト投稿 #hashtag")

        mentions = PostAggregate._create_mentions_from_content_static(post_id, content)

        assert len(mentions) == 2
        mentioned_users = {mention.mentioned_user_name for mention in mentions}
        assert mentioned_users == {"user1", "user2"}

        # 各メンションが正しいpost_idを持つことを確認
        for mention in mentions:
            assert mention.post_id == post_id

    def test_create_mentions_from_content_static_no_mentions(self):
        """メンションを含まないコンテンツのテスト"""
        post_id = PostId(1)
        content = PostContent("メンションなしの投稿 #hashtag")

        mentions = PostAggregate._create_mentions_from_content_static(post_id, content)

        assert len(mentions) == 0

    def test_create_mentions_from_content_static_edge_cases(self):
        """メンション抽出のエッジケーステスト"""
        post_id = PostId(1)

        # 連続する@記号
        content1 = PostContent("@@user1 テスト")
        mentions1 = PostAggregate._create_mentions_from_content_static(post_id, content1)
        assert len(mentions1) == 1
        assert "@user1" in {m.mentioned_user_name for m in mentions1}

        # @の後に記号
        content2 = PostContent("@user1! テスト")
        mentions2 = PostAggregate._create_mentions_from_content_static(post_id, content2)
        assert len(mentions2) == 1
        assert "user1!" in {m.mentioned_user_name for m in mentions2}

        # 複数のスペース
        content3 = PostContent("@user1   @user2")
        mentions3 = PostAggregate._create_mentions_from_content_static(post_id, content3)
        assert len(mentions3) == 2

    def test_content_validation_error_propagation(self):
        """コンテンツバリデーションエラーの伝播テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)

        # 文字数制限を超えるコンテンツ
        long_content = "a" * 281  # 281文字（制限は280文字）
        with pytest.raises(ContentLengthValidationException):
            PostContent(long_content)

        # ハッシュタグ制限を超えるコンテンツ
        many_hashtags = ["#tag"] * 11  # 11個（制限は10個）
        with pytest.raises(HashtagCountValidationException):
            PostContent("content", tuple(many_hashtags))

    def test_boundary_values_content_length(self):
        """コンテンツ文字数の境界値テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)

        # 280文字ちょうど
        exact_content = "a" * 280
        post = PostAggregate.create(post_id, author_user_id, PostContent(exact_content))
        assert post.content.content == exact_content

        # 文字数制限を超えるコンテンツ（例外が発生することを確認済み）
        long_content = "a" * 281
        with pytest.raises(ContentLengthValidationException):
            PostAggregate.create(post_id, author_user_id, PostContent(long_content))

    def test_boundary_values_hashtags(self):
        """ハッシュタグ数の境界値テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)

        # 10個ちょうど
        exact_hashtags = ["#tag"] * 10
        post = PostAggregate.create(post_id, author_user_id, PostContent("content", tuple(exact_hashtags)))
        assert len(post.content.hashtags) == 10

        # ハッシュタグ制限を超える（例外が発生することを確認済み）
        many_hashtags = ["#tag"] * 11
        with pytest.raises(HashtagCountValidationException):
            PostAggregate.create(post_id, author_user_id, PostContent("content", tuple(many_hashtags)))

    def test_event_emission_on_creation(self):
        """作成時のイベント発行テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("@user1 テスト投稿")

        post = PostAggregate.create(post_id, author_user_id, content)

        # イベント発行前の状態
        initial_events = post.get_events()
        assert len(initial_events) == 2  # 作成イベント + メンションイベント

        # 作成イベントの確認
        creation_event = initial_events[0]
        assert creation_event.__class__.__name__ == 'SnsPostCreatedEvent'

        # メンションイベントの確認
        mention_event = initial_events[1]
        assert mention_event.__class__.__name__ == 'SnsContentMentionedEvent'

    def test_event_emission_on_like(self):
        """いいね時のイベント発行テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        # イベント発行前の状態
        initial_event_count = len(post.get_events())

        user_id = UserId(2)
        post.like_post(user_id)

        # イベントが発行されていることを確認
        events = post.get_events()
        assert len(events) == initial_event_count + 1

        # 最新のイベントがいいねイベントであることを確認
        like_event = events[-1]
        assert like_event.__class__.__name__ == 'SnsContentLikedEvent'

    def test_event_emission_on_delete(self):
        """削除時のイベント発行テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        # イベント発行前の状態
        initial_event_count = len(post.get_events())

        # 削除実行
        post.delete_post(author_user_id)

        # イベントが発行されていることを確認
        events = post.get_events()
        assert len(events) == initial_event_count + 1

        # 最新のイベントが削除イベントであることを確認
        delete_event = events[-1]
        assert delete_event.__class__.__name__ == 'SnsContentDeletedEvent'

    def test_full_workflow(self):
        """完全なワークフローのテスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("@user1 @user2 テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        # 初期状態確認
        assert post.deleted is False
        assert len(post.likes) == 0
        assert len(post.get_mentioned_users()) == 2

        # 複数ユーザーによるいいね
        user1_id = UserId(2)
        user2_id = UserId(3)
        post.like_post(user1_id)
        post.like_post(user2_id)

        assert len(post.likes) == 2
        assert post.is_liked_by_user(user1_id) is True
        assert post.is_liked_by_user(user2_id) is True

        # いいね解除
        post.like_post(user1_id)
        assert post.is_liked_by_user(user1_id) is False
        assert len(post.likes) == 1

        # 作成者による削除
        post.delete_post(author_user_id)
        assert post.deleted is True

    def test_invalid_post_id_creation(self):
        """無効なPostIdでの作成エラーテスト"""
        with pytest.raises(PostIdValidationException):
            PostId(0)

        with pytest.raises(PostIdValidationException):
            PostId(-1)

    def test_invalid_user_id_creation(self):
        """無効なUserIdでの作成エラーテスト"""
        with pytest.raises(UserIdValidationException):
            UserId(0)

        with pytest.raises(UserIdValidationException):
            UserId(-1)

    def test_likes_and_mentions_immutability(self):
        """likesとmentionsの不変性テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        # コピーを取得
        likes_copy = post.likes
        mentions_copy = post.mentions

        # コピーを変更しても元のオブジェクトには影響がないことを確認
        likes_copy.add("dummy")
        mentions_copy.add("dummy")

        assert len(post.likes) == 0
        assert len(post.mentions) == 0

    def test_delete_with_likes(self):
        """いいねがある投稿の削除テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        # いいねを追加
        user_id = UserId(2)
        post.like_post(user_id)
        assert len(post.likes) == 1

        # 削除実行
        post.delete_post(author_user_id)
        assert post.deleted is True

        # 削除後もいいね状態は保持される（ビジネスルールによる）
        assert len(post.likes) == 1
        assert post.is_liked_by_user(user_id) is True

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

    def test_reply_ids_immutability(self):
        """reply_idsの不変性テスト"""
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿")
        post = PostAggregate.create(post_id, author_user_id, content)

        # コピーを取得
        reply_ids_copy = post.reply_ids

        # コピーを変更しても元のオブジェクトには影響がないことを確認
        from ai_rpg_world.domain.sns.value_object import ReplyId
        reply_ids_copy.add(ReplyId(1))

        assert len(post.reply_ids) == 0

    def test_get_display_info(self):
        """get_display_info()メソッドのテスト"""
        from ai_rpg_world.domain.sns.value_object import ReplyId
        post_id = PostId(1)
        author_user_id = UserId(1)
        content = PostContent("テスト投稿", hashtags=("#test",), visibility=PostVisibility.PUBLIC)
        post = PostAggregate.create(post_id, author_user_id, content)

        # いいねとリプライを追加
        user_id = UserId(2)
        post.like_post(user_id)
        post.add_reply(ReplyId(1))
        post.add_reply(ReplyId(2))

        viewer_user_id = UserId(3)
        display_info = post.get_display_info(viewer_user_id)

        assert display_info["post_id"] == 1
        assert display_info["author_user_id"] == 1
        assert display_info["content"] == "テスト投稿"
        assert display_info["hashtags"] == ["#test"]
        assert display_info["visibility"] == "public"
        assert display_info["like_count"] == 1
        assert display_info["reply_count"] == 2
        assert display_info["is_liked_by_viewer"] is False  # viewerはいいねしていない
        assert display_info["is_replied_by_viewer"] is False  # ポストには直接リプライできない
        assert display_info["mentioned_users"] == []
        assert display_info["is_deleted"] is False
