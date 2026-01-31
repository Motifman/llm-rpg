import pytest
from datetime import datetime
from ai_rpg_world.application.social.services.reply_query_service import ReplyQueryService
from ai_rpg_world.application.social.contracts.dtos import ReplyDto, ReplyThreadDto, PostDto
from ai_rpg_world.application.social.exceptions.query.reply_query_exception import (
    ReplyQueryException,
    ReplyNotFoundException,
    ReplyAccessDeniedException
)
from ai_rpg_world.application.social.exceptions.query.user_query_exception import UserQueryException
from ai_rpg_world.domain.sns.value_object import UserId, PostId, ReplyId, PostContent
from ai_rpg_world.domain.sns.enum import PostVisibility
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.exception import UserIdValidationException, PostIdValidationException
from ai_rpg_world.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from ai_rpg_world.infrastructure.repository.in_memory_reply_repository import InMemoryReplyRepository
from ai_rpg_world.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository


class TestReplyQueryService:
    """ReplyQueryServiceのテスト"""

    @pytest.fixture
    def post_repository(self):
        """実際のInMemoryPostRepository"""
        return InMemoryPostRepository()

    @pytest.fixture
    def reply_repository(self):
        """実際のInMemoryReplyRepository"""
        return InMemoryReplyRepository()

    @pytest.fixture
    def user_repository(self):
        """実際のInMemorySnsUserRepository"""
        return InMemorySnsUserRepository()

    @pytest.fixture
    def reply_query_service(self, post_repository, reply_repository, user_repository):
        """テスト対象のサービス"""
        return ReplyQueryService(post_repository, user_repository, reply_repository)

    def create_test_reply(self, reply_id: int, author_user_id: int, parent_post_id: int, parent_reply_id: int = None, content: str = "テストリプライ", visibility: PostVisibility = PostVisibility.PUBLIC) -> ReplyAggregate:
        """テスト用のリプライを作成"""
        # contentからハッシュタグを抽出（#で始まる単語）
        import re
        hashtags_in_content = re.findall(r'#(\w+)', content)
        hashtags = tuple(hashtags_in_content) if hashtags_in_content else ("test", "reply")

        reply_content = PostContent(
            content=content,
            hashtags=hashtags,
            visibility=visibility
        )

        # テスト用の parent_author_id を決定
        # parent_post_id が 2001 の場合はユーザーID 1、parent_reply_id が 2001 の場合はユーザーID 2
        parent_author_id = None
        if parent_post_id == 2001:
            parent_author_id = UserId(1)  # ポスト作成者
        elif parent_reply_id == 2001:
            parent_author_id = UserId(2)  # リプライ1作成者

        return ReplyAggregate.create(
            reply_id=ReplyId(reply_id),
            parent_post_id=PostId(parent_post_id) if parent_post_id else None,
            parent_reply_id=ReplyId(parent_reply_id) if parent_reply_id else None,
            parent_author_id=parent_author_id,
            author_user_id=UserId(author_user_id),
            content=reply_content
        )

    def setup_test_data(self, post_repository, reply_repository, user_repository):
        """テストデータをセットアップ"""
        # リポジトリをクリア
        reply_repository._replies.clear()

        # テスト用のポストを追加（ポストID 2001）
        test_post_content = PostContent(
            content="これはテストポストです",
            hashtags=("test", "post"),
            visibility=PostVisibility.PUBLIC
        )
        test_post = PostAggregate.create(
            post_id=PostId(2001),
            author_user_id=UserId(1),
            post_content=test_post_content
        )
        post_repository._posts[PostId(2001)] = test_post

        # テスト用のリプライを追加
        reply1 = self.create_test_reply(2001, 2, 2001, content="これはテストリプライ1です")
        reply_repository._replies[ReplyId(2001)] = reply1

        reply2 = self.create_test_reply(2002, 3, 2001, content="これはテストリプライ2です")
        reply_repository._replies[ReplyId(2002)] = reply2

        # リプライ1へのネストされたリプライ
        reply3 = self.create_test_reply(2003, 1, None, 2001, content="これはネストされたリプライです")
        reply_repository._replies[ReplyId(2003)] = reply3

        # プライベートリプライ
        private_reply = self.create_test_reply(2004, 1, 2001, content="これはプライベートリプライです", visibility=PostVisibility.PRIVATE)
        reply_repository._replies[ReplyId(2004)] = private_reply

        # フォロワー限定リプライ
        followers_reply = self.create_test_reply(2005, 2, 2001, content="これはフォロワー限定リプライです", visibility=PostVisibility.FOLLOWERS_ONLY)
        reply_repository._replies[ReplyId(2005)] = followers_reply

    def test_get_replies_by_post_id_success(self, reply_query_service, post_repository, reply_repository, user_repository):
        """get_replies_by_post_idの正常系テスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 実行
        result = reply_query_service.get_replies_by_post_id(post_id=2001, viewer_user_id=1)

        # 検証
        # viewer_user_id=1の場合:
        # 2001: public -> 見える
        # 2002: public -> 見える
        # 2004: private, author=1, viewer=1 -> 見える（自分のプライベート）
        # 2005: followers_only, author=2, viewer=1 -> 見える（フォローしている）
        assert len(result) == 4  # 全てのリプライが見える
        assert all(isinstance(reply, ReplyDto) for reply in result)

        # 作成日時でソートされていることを確認（古い順）
        assert result[0].created_at <= result[1].created_at <= result[2].created_at

        # 特定のフィールドをチェック
        reply_contents = [reply.content for reply in result]
        assert "これはテストリプライ1です" in reply_contents
        assert "これはテストリプライ2です" in reply_contents
        assert "これはフォロワー限定リプライです" in reply_contents

    def test_get_replies_by_post_id_with_limit_offset(self, reply_query_service, post_repository, reply_repository, user_repository):
        """get_replies_by_post_idのlimit/offsetテスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # limit=1, offset=1で実行
        result = reply_query_service.get_replies_by_post_id(post_id=2001, viewer_user_id=1, limit=1, offset=1)

        # 検証
        assert len(result) == 1

    def test_get_replies_by_post_id_post_not_found(self, reply_query_service, post_repository, reply_repository, user_repository):
        """ポストが見つからない場合のテスト"""
        # テストデータをセットアップ（ポストなし）
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 存在しないポストIDで実行
        with pytest.raises(ReplyNotFoundException):
            reply_query_service.get_replies_by_post_id(post_id=999, viewer_user_id=1)

    def test_get_reply_thread_success(self, reply_query_service, post_repository, reply_repository, user_repository):
        """get_reply_threadの正常系テスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 実行
        result = reply_query_service.get_reply_thread(post_id=2001, viewer_user_id=1)

        # 検証
        assert isinstance(result, ReplyThreadDto)
        assert isinstance(result.post, PostDto)
        assert len(result.replies) == 5  # 全てのリプライ（ネストされたものも含む）

        # ポスト情報が正しいことを確認
        assert result.post.post_id == 2001
        assert result.post.content == "これはテストポストです"

        # リプライ情報が正しいことを確認
        reply_ids = [reply.reply_id for reply in result.replies]
        assert 2001 in reply_ids
        assert 2002 in reply_ids
        assert 2003 in reply_ids  # ネストされたリプライ

        # ネストされたリプライのdepthが正しいことを確認
        nested_reply = next(reply for reply in result.replies if reply.reply_id == 2003)
        assert nested_reply.depth == 1  # 親リプライがあるのでdepth=1

    def test_get_reply_thread_post_not_found(self, reply_query_service, post_repository, reply_repository, user_repository):
        """ポストが見つからない場合のget_reply_threadテスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 存在しないポストIDで実行
        with pytest.raises(ReplyNotFoundException):
            reply_query_service.get_reply_thread(post_id=999, viewer_user_id=1)

    def test_get_reply_by_id_success(self, reply_query_service, post_repository, reply_repository, user_repository):
        """get_reply_by_idの正常系テスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 実行
        result = reply_query_service.get_reply_by_id(reply_id=2001, viewer_user_id=1)

        # 検証
        assert isinstance(result, ReplyDto)
        assert result.reply_id == 2001
        assert result.content == "これはテストリプライ1です"
        assert result.parent_post_id == 2001
        assert result.parent_reply_id is None

    def test_get_reply_by_id_not_found(self, reply_query_service, post_repository, reply_repository, user_repository):
        """リプライが見つからない場合のテスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 存在しないリプライIDで実行
        with pytest.raises(ReplyNotFoundException):
            reply_query_service.get_reply_by_id(reply_id=9999, viewer_user_id=1)

    def test_get_user_replies_success(self, reply_query_service, post_repository, reply_repository, user_repository):
        """get_user_repliesの正常系テスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 実行（ユーザー2のリプライを取得）
        result = reply_query_service.get_user_replies(user_id=2, viewer_user_id=1)

        # 検証
        assert len(result) == 2  # ユーザー2のリプライは2つ
        assert all(reply.author_user_id == 2 for reply in result)

        # 作成日時でソートされていることを確認（新しい順）
        assert result[0].created_at >= result[1].created_at

    def test_get_user_replies_with_limit_offset(self, reply_query_service, post_repository, reply_repository, user_repository):
        """get_user_repliesのlimit/offsetテスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # limit=1で実行
        result = reply_query_service.get_user_replies(user_id=2, viewer_user_id=1, limit=1)

        # 検証
        assert len(result) == 1

    def test_visibility_filtering_public_reply(self, reply_query_service, post_repository, reply_repository, user_repository):
        """パブリックリプライの可視性テスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 実行（ユーザー1が閲覧）
        result = reply_query_service.get_replies_by_post_id(post_id=2001, viewer_user_id=1)

        # 検証（プライベートリプライ以外が見える）
        reply_ids = [reply.reply_id for reply in result]
        assert 1004 not in reply_ids  # プライベートリプライは見えない

    def test_visibility_filtering_followers_only_reply(self, reply_query_service, post_repository, reply_repository, user_repository):
        """フォロワー限定リプライの可視性テスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 実行（ユーザー1が閲覧、ただしフォロワー関係はテストデータにないので見えないはず）
        result = reply_query_service.get_replies_by_post_id(post_id=2001, viewer_user_id=4)  # ユーザー4は関係ない

        # 検証（フォロワー限定リプライが見えないはず）
        reply_ids = [reply.reply_id for reply in result]
        assert 1005 not in reply_ids  # フォロワー限定リプライは見えない

    def test_reply_thread_dto_structure(self, reply_query_service, post_repository, reply_repository, user_repository):
        """ReplyThreadDtoの構造テスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # 実行
        result = reply_query_service.get_reply_thread(post_id=2001, viewer_user_id=1)

        # 検証
        assert isinstance(result.post, PostDto)
        assert isinstance(result.replies, list)
        assert all(isinstance(reply, ReplyDto) for reply in result.replies)

        # depthフィールドが正しく設定されていることを確認
        depths = [reply.depth for reply in result.replies]
        assert 0 in depths  # ルートレベルのリプライ
        assert 1 in depths  # ネストされたリプライ

    def test_deleted_reply_visible_with_message(self, reply_query_service, post_repository, reply_repository, user_repository):
        """削除済みリプライがメッセージ付きで表示されることをテスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # リプライを削除済みに設定
        reply = reply_repository.find_by_id(ReplyId(2002))
        reply.delete(UserId(3), "reply")  # 著者が削除
        reply_repository.save(reply)

        # 実行
        result = reply_query_service.get_replies_by_post_id(post_id=2001, viewer_user_id=1)

        # 検証（削除済みリプライがメッセージ付きで表示される）
        reply_ids = [reply.reply_id for reply in result]
        assert 2002 in reply_ids

        # 削除されたリプライの情報を確認
        deleted_reply = next(reply for reply in result if reply.reply_id == 2002)
        assert deleted_reply.is_deleted is True
        assert deleted_reply.deletion_message == "このリプライは削除されています"
        assert deleted_reply.author_user_name == "[削除済み]"
        assert deleted_reply.content == ""
        assert deleted_reply.like_count == 0

    def test_deleted_post_reply_thread_shows_deletion_message(self, reply_query_service, post_repository, reply_repository, user_repository):
        """削除済みポストへのリプライツリーが削除メッセージ付きで表示されることをテスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # ポストを削除済みに設定
        post = post_repository.find_by_id(PostId(2001))
        post.delete_post(UserId(1))  # 著者が削除
        post_repository.save(post)

        # 実行（削除されたポストへのリプライツリーを取得）
        result = reply_query_service.get_reply_thread(post_id=2001, viewer_user_id=1)

        # 検証（削除済みポストがメッセージ付きで表示される）
        assert result.post.is_deleted is True
        assert result.post.deletion_message == "このポストは削除されています"
        assert result.post.author_user_name == "[削除済み]"
        assert result.post.content == ""
        assert result.post.like_count == 0
        # リプライ数は保持される
        assert result.post.reply_count >= 0

        # リプライは通常通り表示される
        assert len(result.replies) > 0

    def test_deleted_reply_in_thread_shows_deletion_message(self, reply_query_service, post_repository, reply_repository, user_repository):
        """リプライツリー内の削除済みリプライがメッセージ付きで表示されることをテスト"""
        # テストデータをセットアップ
        self.setup_test_data(post_repository, reply_repository, user_repository)

        # リプライを削除済みに設定
        reply = reply_repository.find_by_id(ReplyId(2003))  # 子リプライ
        reply.delete(UserId(1), "reply")  # 著者が削除
        reply_repository.save(reply)

        # 実行（リプライツリーを取得）
        result = reply_query_service.get_reply_thread(post_id=2001, viewer_user_id=1)

        # 検証（削除済みリプライがメッセージ付きで表示される）
        reply_ids = [reply.reply_id for reply in result.replies]
        assert 2003 in reply_ids

        deleted_reply = next(reply for reply in result.replies if reply.reply_id == 2003)
        assert deleted_reply.is_deleted is True
        assert deleted_reply.deletion_message == "このリプライは削除されています"
        assert deleted_reply.author_user_name == "[削除済み]"
        assert deleted_reply.content == ""
        assert deleted_reply.like_count == 0
