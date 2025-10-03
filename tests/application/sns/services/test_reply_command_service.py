"""
ReplyCommandServiceのテスト
"""
import pytest
import logging
from unittest.mock import Mock, patch
from src.application.sns.services.reply_command_service import ReplyCommandService
from src.infrastructure.repository.in_memory_post_repository_with_uow import InMemoryPostRepositoryWithUow
from src.infrastructure.repository.in_memory_sns_user_repository_with_uow import InMemorySnsUserRepositoryWithUow
from src.infrastructure.repository.in_memory_reply_repository_with_uow import InMemoryReplyRepositoryWithUow
from src.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from src.application.sns.contracts.commands import (
    CreateReplyCommand,
    LikeReplyCommand,
    DeleteReplyCommand,
    CreatePostCommand
)
from src.application.sns.contracts.dtos import CommandResultDto
from src.application.sns.exceptions.command.reply_command_exception import (
    ReplyCommandException,
    ReplyCreationException,
    ReplyDeletionException,
    ReplyLikeException,
    ReplyNotFoundForCommandException,
    ReplyOwnershipException,
)
from src.application.sns.exceptions.query.user_query_exception import UserQueryException
from src.application.sns.exceptions import SystemErrorException
from src.domain.sns.exception import (
    UserNotFoundException,
    ContentLengthValidationException,
    HashtagCountValidationException,
    VisibilityValidationException,
)
from src.domain.sns.value_object import UserId, PostId, ReplyId
from src.domain.sns.enum import PostVisibility
from src.domain.sns.event import SnsReplyCreatedEvent, SnsContentLikedEvent, SnsContentDeletedEvent, SnsContentMentionedEvent


class TestReplyCommandService:
    """ReplyCommandServiceのテストクラス"""

    @pytest.fixture
    def setup_service(self):
        """テスト用のサービスとリポジトリをセットアップ"""
        # Unit of Workファクトリ関数を定義（別トランザクション用）
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        # ファクトリーメソッドでUnit of Workとイベントパブリッシャーを作成
        unit_of_work, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )

        post_repository = InMemoryPostRepositoryWithUow(unit_of_work)
        user_repository = InMemorySnsUserRepositoryWithUow(unit_of_work)
        reply_repository = InMemoryReplyRepositoryWithUow(unit_of_work)

        service = ReplyCommandService(post_repository, user_repository, reply_repository, event_publisher, unit_of_work)

        return service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work

    def test_create_reply_to_post_success(self, setup_service):
        """ポストへのリプライ作成成功のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        # リプライを作成
        command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )

        result = service.create_reply(command)

        # 結果の検証
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "リプライが正常に作成されました"
        assert "reply_id" in result.data
        assert isinstance(result.data["reply_id"], int)

        # リポジトリに保存されていることを確認
        reply_id = ReplyId(result.data["reply_id"])
        saved_reply = reply_repository.find_by_id(reply_id)
        assert saved_reply is not None
        assert saved_reply.author_user_id.value == 1
        assert saved_reply.content.content == "テストリプライ"
        assert saved_reply.parent_post_id.value == post_id
        assert saved_reply.parent_reply_id is None

        # 親ポストにリプライが追加されていることを確認
        saved_post = post_repository.find_by_id(PostId(post_id))
        assert reply_id in saved_post.reply_ids

    def test_create_reply_to_reply_success(self, setup_service):
        """リプライへのリプライ作成成功のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        # まず親リプライを作成
        parent_reply_command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="親リプライ",
            visibility=PostVisibility.PUBLIC
        )
        parent_reply_result = service.create_reply(parent_reply_command)
        parent_reply_id = parent_reply_result.data["reply_id"]

        # 子リプライを作成
        command = CreateReplyCommand(
            user_id=1,
            parent_reply_id=parent_reply_id,
            content="子リプライ",
            visibility=PostVisibility.PUBLIC
        )

        result = service.create_reply(command)

        # 結果の検証
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "リプライが正常に作成されました"
        assert "reply_id" in result.data
        assert isinstance(result.data["reply_id"], int)

        # リポジトリに保存されていることを確認
        reply_id = ReplyId(result.data["reply_id"])
        saved_reply = reply_repository.find_by_id(reply_id)
        assert saved_reply is not None
        assert saved_reply.author_user_id.value == 1
        assert saved_reply.content.content == "子リプライ"
        assert saved_reply.parent_post_id is None
        assert saved_reply.parent_reply_id.value == parent_reply_id

        # 親リプライに子リプライが追加されていることを確認
        saved_parent_reply = reply_repository.find_by_id(ReplyId(parent_reply_id))
        assert reply_id in saved_parent_reply.reply_ids

    def test_create_reply_user_not_found(self, setup_service):
        """存在しないユーザーがリプライ作成しようとした場合のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        command = CreateReplyCommand(
            user_id=999,  # 存在しないユーザー
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )

        with pytest.raises(UserQueryException):  # ApplicationExceptionFactoryによって変換される
            service.create_reply(command)

    def test_create_reply_parent_post_not_found(self, setup_service):
        """存在しない親ポストへのリプライ作成のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        command = CreateReplyCommand(
            user_id=1,
            parent_post_id=999,  # 存在しないポスト
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )

        with pytest.raises(ReplyCreationException) as exc_info:
            service.create_reply(command)

        assert "親ポストが見つかりません" in str(exc_info.value)

    def test_create_reply_parent_reply_not_found(self, setup_service):
        """存在しない親リプライへのリプライ作成のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        command = CreateReplyCommand(
            user_id=1,
            parent_reply_id=999,  # 存在しないリプライ
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )

        with pytest.raises(ReplyCreationException) as exc_info:
            service.create_reply(command)

        assert "親リプライが見つかりません" in str(exc_info.value)

    def test_create_reply_no_parent_specified(self, setup_service):
        """親ポストも親リプライも指定されていない場合のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        command = CreateReplyCommand(
            user_id=1,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )

        with pytest.raises(ReplyCreationException) as exc_info:
            service.create_reply(command)

        assert "親ポストまたは親リプライのどちらかを指定する必要があります" in str(exc_info.value)

    def test_like_reply_success(self, setup_service):
        """リプライいいね成功のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストとリプライを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        create_reply_command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )
        reply_result = service.create_reply(create_reply_command)
        reply_id = reply_result.data["reply_id"]

        # いいねコマンドを実行
        like_command = LikeReplyCommand(
            user_id=1,
            reply_id=reply_id
        )

        result = service.like_reply(like_command)

        # 結果の検証
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "リプライにいいねしました"
        assert result.data["reply_id"] == reply_id
        assert result.data["user_id"] == 1

        # リプライにいいねが追加されていることを確認
        saved_reply = reply_repository.find_by_id(ReplyId(reply_id))
        assert saved_reply.is_liked_by_user(UserId(1))

    def test_like_reply_not_found(self, setup_service):
        """存在しないリプライにいいねしようとした場合のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        like_command = LikeReplyCommand(
            user_id=1,
            reply_id=999  # 存在しないリプライ
        )

        with pytest.raises(ReplyNotFoundForCommandException):
            service.like_reply(like_command)

    def test_delete_reply_success(self, setup_service):
        """リプライ削除成功のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストとリプライを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        create_reply_command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )
        reply_result = service.create_reply(create_reply_command)
        reply_id = reply_result.data["reply_id"]

        # 削除コマンドを実行
        delete_command = DeleteReplyCommand(
            user_id=1,
            reply_id=reply_id
        )

        result = service.delete_reply(delete_command)

        # 結果の検証
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "リプライが正常に削除されました"
        assert result.data["reply_id"] == reply_id
        assert result.data["user_id"] == 1

        # リプライが削除されていることを確認
        saved_reply = reply_repository.find_by_id(ReplyId(reply_id))
        assert saved_reply.deleted

        # 親ポストからリプライが削除されていることを確認
        saved_post = post_repository.find_by_id(PostId(post_id))
        assert ReplyId(reply_id) not in saved_post.reply_ids

    def test_delete_reply_not_found(self, setup_service):
        """存在しないリプライを削除しようとした場合のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        delete_command = DeleteReplyCommand(
            user_id=1,
            reply_id=999  # 存在しないリプライ
        )

        with pytest.raises(ReplyNotFoundForCommandException):
            service.delete_reply(delete_command)

    def test_delete_reply_ownership_exception(self, setup_service):
        """他人のリプライを削除しようとした場合のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストとリプライを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        create_reply_command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )
        reply_result = service.create_reply(create_reply_command)
        reply_id = reply_result.data["reply_id"]

        # 別のユーザー（ユーザー2）で削除を試みる
        delete_command = DeleteReplyCommand(
            user_id=2,  # 別のユーザー
            reply_id=reply_id
        )

        with pytest.raises(ReplyOwnershipException):
            service.delete_reply(delete_command)

    def test_create_reply_content_too_long(self, setup_service):
        """コンテンツが長すぎる場合のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        # 281文字のコンテンツ（上限を超える）
        long_content = "a" * 281
        command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content=long_content,
            visibility=PostVisibility.PUBLIC
        )

        from src.application.sns.exceptions.command.post_command_exception import PostCommandException
        with pytest.raises(PostCommandException):  # ContentLengthValidationExceptionが変換される
            service.create_reply(command)

    def test_create_reply_invalid_visibility(self, setup_service):
        """無効な可視性のテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="テストリプライ",
            visibility="invalid_visibility"  # 無効な可視性
        )

        from src.application.sns.exceptions.command.post_command_exception import PostCommandException
        with pytest.raises(PostCommandException):  # VisibilityValidationExceptionが変換される
            service.create_reply(command)

    def test_create_reply_events_published(self, setup_service):
        """リプライ作成時にイベントが発行されることを確認"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        # ポスト作成時のイベントをクリア
        event_publisher.clear_events()

        # リプライを作成
        command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )

        result = service.create_reply(command)

        # イベントが発行されたことを確認
        published_events = event_publisher.get_published_events()
        assert len(published_events) >= 1  # 少なくとも1つのイベントが発行されている

        # SnsReplyCreatedEventが含まれていることを確認
        created_events = [e for e in published_events if isinstance(e, SnsReplyCreatedEvent)]
        assert len(created_events) >= 1

        # イベントの内容を確認
        event = created_events[0]
        assert event.author_user_id.value == 1

    def test_like_reply_events_published(self, setup_service):
        """リプライいいね時にイベントが発行されることを確認"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストとリプライを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        create_reply_command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )
        reply_result = service.create_reply(create_reply_command)
        reply_id = reply_result.data["reply_id"]

        # いいねを実行
        like_command = LikeReplyCommand(
            user_id=1,
            reply_id=reply_id
        )

        # イベント発行をリセット（作成時のイベントをクリア）
        event_publisher.clear_events()

        result = service.like_reply(like_command)

        # イベントが発行されたことを確認
        published_events = event_publisher.get_published_events()
        assert len(published_events) >= 1

        # SnsContentLikedEventが含まれていることを確認
        liked_events = [e for e in published_events if isinstance(e, SnsContentLikedEvent)]
        assert len(liked_events) >= 1

        # イベントの内容を確認
        event = liked_events[0]
        assert event.content_type == "reply"
        assert event.user_id.value == 1

    def test_delete_reply_events_published(self, setup_service):
        """リプライ削除時にイベントが発行されることを確認"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストとリプライを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        create_reply_command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )
        reply_result = service.create_reply(create_reply_command)
        reply_id = reply_result.data["reply_id"]

        # ポスト作成時とリプライ作成時のイベントをリセット
        event_publisher.clear_events()

        # 削除を実行
        delete_command = DeleteReplyCommand(
            user_id=1,
            reply_id=reply_id
        )

        result = service.delete_reply(delete_command)

        # イベントが発行されたことを確認
        published_events = event_publisher.get_published_events()
        assert len(published_events) >= 1

        # SnsContentDeletedEventが含まれていることを確認
        deleted_events = [e for e in published_events if isinstance(e, SnsContentDeletedEvent)]
        assert len(deleted_events) >= 1

        # イベントの内容を確認
        event = deleted_events[0]
        assert event.content_type == "reply"
        assert event.author_user_id.value == 1

    def test_create_reply_system_error_handling(self, setup_service):
        """システムエラー（リポジトリ例外）のハンドリングテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        # リポジトリのsaveメソッドをモックして例外を投げる
        original_save = reply_repository.save
        def mock_save_that_raises(reply):
            raise Exception("Database connection failed")

        reply_repository.save = mock_save_that_raises

        try:
            command = CreateReplyCommand(
                user_id=1,
                parent_post_id=post_id,
                content="テストリプライ",
                visibility=PostVisibility.PUBLIC
            )

            with pytest.raises(SystemErrorException) as exc_info:
                service.create_reply(command)

            assert "Database connection failed" in str(exc_info.value)
        finally:
            # モックを元に戻す
            reply_repository.save = original_save

    def test_like_reply_system_error_handling(self, setup_service):
        """いいね時のシステムエラーハンドリングテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストとリプライを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        create_reply_command = CreateReplyCommand(
            user_id=1,
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )
        reply_result = service.create_reply(create_reply_command)
        reply_id = reply_result.data["reply_id"]

        # リポジトリのsaveメソッドをモックして例外を投げる
        original_save = reply_repository.save
        def mock_save_that_raises(reply):
            raise Exception("Database connection failed")

        reply_repository.save = mock_save_that_raises

        try:
            like_command = LikeReplyCommand(
                user_id=1,
                reply_id=reply_id
            )

            with pytest.raises(SystemErrorException) as exc_info:
                service.like_reply(like_command)

            assert "Database connection failed" in str(exc_info.value)
        finally:
            # モックを元に戻す
            reply_repository.save = original_save

    def test_transaction_rollback_on_failure(self, setup_service):
        """トランザクション失敗時のロールバックテスト"""
        service, post_repository, user_repository, reply_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        from src.application.sns.services.post_command_service import PostCommandService
        post_service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)
        create_post_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        post_result = post_service.create_post(create_post_command)
        post_id = post_result.data["post_id"]

        # リプライ作成前にリポジトリの状態を保存
        initial_reply_count = len(reply_repository._replies)

        # 存在しないユーザーIDでリプライを作成（失敗するはず）
        command = CreateReplyCommand(
            user_id=999,  # 存在しないユーザー
            parent_post_id=post_id,
            content="テストリプライ",
            visibility=PostVisibility.PUBLIC
        )

        # 例外が発生することを確認
        from src.application.sns.exceptions.query.user_query_exception import UserQueryException
        with pytest.raises(UserQueryException):
            service.create_reply(command)

        # リプライが作成されていないことを確認（ロールバックされた）
        assert len(reply_repository._replies) == initial_reply_count

        # Unit of Workがロールバックされたことを確認
        assert unit_of_work.is_committed() is False
        assert unit_of_work.is_in_transaction() is False
