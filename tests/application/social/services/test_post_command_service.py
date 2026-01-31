"""
PostCommandServiceのテスト
"""
import pytest
import logging
from unittest.mock import Mock, patch
from src.application.social.services.post_command_service import PostCommandService
from src.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from src.infrastructure.events.in_memory_event_publisher_with_uow import InMemoryEventPublisherWithUow
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from src.application.social.contracts.commands import (
    CreatePostCommand,
    LikePostCommand,
    DeletePostCommand
)
from src.application.social.contracts.dtos import CommandResultDto
from src.application.social.exceptions.command.post_command_exception import (
    PostCommandException,
    PostCreationException,
    PostDeletionException,
    PostLikeException,
    PostNotFoundForCommandException,
    PostOwnershipException,
)
from src.application.social.exceptions.query.user_query_exception import UserQueryException
from src.application.social.exceptions import SystemErrorException
from src.domain.sns.exception import (
    UserNotFoundException,
    ContentLengthValidationException,
    HashtagCountValidationException,
    VisibilityValidationException,
)
from src.domain.sns.value_object import UserId, PostId
from src.domain.sns.enum import PostVisibility
from src.domain.sns.event import SnsPostCreatedEvent, SnsContentLikedEvent, SnsContentDeletedEvent, SnsContentMentionedEvent


class TestPostCommandService:
    """PostCommandServiceのテストクラス"""

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

        data_store = InMemoryDataStore()
        post_repository = InMemoryPostRepository(data_store, unit_of_work)
        user_repository = InMemorySnsUserRepository(data_store, unit_of_work)

        service = PostCommandService(post_repository, user_repository, event_publisher, unit_of_work)

        return service, post_repository, user_repository, event_publisher, unit_of_work

    def test_create_post_success(self, setup_service):
        """ポスト作成成功のテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )

        result = service.create_post(command)

        # 結果の検証
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ポストが正常に作成されました"
        assert "post_id" in result.data
        assert isinstance(result.data["post_id"], int)

        # リポジトリに保存されていることを確認
        post_id = PostId(result.data["post_id"])
        saved_post = post_repository.find_by_id(post_id.value)
        assert saved_post is not None
        assert saved_post.author_user_id.value == 1
        assert saved_post.post_content.content == "テストポスト"
        assert saved_post.post_content.visibility == PostVisibility.PUBLIC

    def test_create_post_user_not_found(self, setup_service):
        """存在しないユーザーがポスト作成しようとした場合のテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        command = CreatePostCommand(
            user_id=999,  # 存在しないユーザー
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )

        with pytest.raises(UserQueryException):  # ApplicationExceptionFactoryによって変換される
            service.create_post(command)

    def test_like_post_success(self, setup_service):
        """ポストいいね成功のテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        create_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        create_result = service.create_post(create_command)
        post_id = create_result.data["post_id"]

        # いいねコマンド
        like_command = LikePostCommand(
            post_id=post_id,
            user_id=1
        )

        result = service.like_post(like_command)

        # 結果の検証
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ポストにいいねしました"
        assert result.data["post_id"] == post_id
        assert result.data["user_id"] == 1

        # いいねが保存されていることを確認
        post = post_repository.find_by_id(post_id)
        assert post.is_liked_by_user(UserId(1))

    def test_like_post_not_found(self, setup_service):
        """存在しないポストにいいねしようとした場合のテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        command = LikePostCommand(
            post_id=999,  # 存在しないポスト
            user_id=1
        )

        with pytest.raises(PostCommandException):  # PostNotFoundForCommandExceptionが変換される
            service.like_post(command)

    def test_delete_post_success(self, setup_service):
        """ポスト削除成功のテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        create_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        create_result = service.create_post(create_command)
        post_id = create_result.data["post_id"]

        # 削除コマンド
        delete_command = DeletePostCommand(
            post_id=post_id,
            user_id=1
        )

        result = service.delete_post(delete_command)

        # 結果の検証
        assert isinstance(result, CommandResultDto)
        assert result.success is True
        assert result.message == "ポストが正常に削除されました"
        assert result.data["post_id"] == post_id
        assert result.data["user_id"] == 1

        # 削除されていることを確認
        post = post_repository.find_by_id(post_id)
        assert post.deleted is True

    def test_delete_post_not_found(self, setup_service):
        """存在しないポストを削除しようとした場合のテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        command = DeletePostCommand(
            post_id=999,  # 存在しないポスト
            user_id=1
        )

        with pytest.raises(PostCommandException):  # PostNotFoundForCommandExceptionが変換される
            service.delete_post(command)

    def test_delete_post_ownership_error(self, setup_service):
        """他人のポストを削除しようとした場合のテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        create_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        create_result = service.create_post(create_command)
        post_id = create_result.data["post_id"]

        # 別のユーザー（既存のユーザー2）で削除コマンド
        delete_command = DeletePostCommand(
            post_id=post_id,
            user_id=2  # 作成者ではないユーザー
        )

        with pytest.raises(PostCommandException):  # PostOwnershipExceptionが変換される
            service.delete_post(delete_command)

    def test_delete_post_already_deleted(self, setup_service):
        """すでに削除されたポストを削除しようとした場合のテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        # まずポストを作成
        create_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        create_result = service.create_post(create_command)
        post_id = create_result.data["post_id"]

        # 1回目の削除（成功）
        delete_command = DeletePostCommand(post_id=post_id, user_id=1)
        result1 = service.delete_post(delete_command)

        # 結果の検証
        assert isinstance(result1, CommandResultDto)
        assert result1.success is True
        assert result1.message == "ポストが正常に削除されました"
        assert result1.data["post_id"] == post_id
        assert result1.data["user_id"] == 1

        # 削除されていることを確認
        post = post_repository.find_by_id(post_id)
        assert post.deleted is True

        # 2回目の削除（すでに削除済みなので失敗）
        with pytest.raises(PostCommandException):  # ContentAlreadyDeletedExceptionが変換される
            service.delete_post(delete_command)

    def test_unexpected_exception_handling(self, setup_service):
        """予期せぬ例外が発生した場合のテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        # リポジトリのsaveメソッドで例外を発生させる
        with patch.object(post_repository, 'save', side_effect=Exception("Unexpected error")):
            command = CreatePostCommand(
                user_id=1,
                content="テストポスト",
                visibility=PostVisibility.PUBLIC
            )

            with pytest.raises(SystemErrorException):
                service.create_post(command)

    def test_create_post_content_too_long(self, setup_service):
        """コンテンツ長超過のテスト"""
        service, _, _, _, _ = setup_service

        command = CreatePostCommand(
            user_id=1,
            content="x" * 281,  # 281文字（上限280）
            visibility=PostVisibility.PUBLIC
        )

        with pytest.raises(PostCommandException):  # ContentLengthValidationExceptionが変換される
            service.create_post(command)

    def test_create_post_too_many_hashtags(self, setup_service):
        """ハッシュタグ数超過のテスト"""
        service, _, _, _, _ = setup_service

        # 11個のハッシュタグ（上限10）
        hashtags = " ".join([f"#tag{i}" for i in range(11)])
        content = f"Test content {hashtags}"

        command = CreatePostCommand(
            user_id=1,
            content=content,
            visibility=PostVisibility.PUBLIC
        )

        with pytest.raises(PostCommandException):  # HashtagCountValidationExceptionが変換される
            service.create_post(command)

    def test_create_post_invalid_visibility(self, setup_service):
        """無効な可視性のテスト"""
        service, _, _, _, _ = setup_service

        # PostVisibilityではない値を直接渡すことはできないので、
        # モックを使ってPostContent.createがVisibilityValidationExceptionを投げるようにする
        with patch('src.domain.sns.value_object.post_content.PostContent.create') as mock_create:
            mock_create.side_effect = VisibilityValidationException("invalid_visibility")

            command = CreatePostCommand(
                user_id=1,
                content="test",
                visibility=PostVisibility.PUBLIC  # 実際には無効な値になるようモック
            )

            with pytest.raises(PostCommandException):  # VisibilityValidationExceptionが変換される
                service.create_post(command)

    def test_like_post_toggle_behavior(self, setup_service):
        """いいねのトグル動作テスト（2回押すと解除される）"""
        service, post_repository, _, _, _ = setup_service

        # まずポストを作成
        create_command = CreatePostCommand(
            user_id=1,
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )
        create_result = service.create_post(create_command)
        post_id = create_result.data["post_id"]

        # 初回いいね
        like_command = LikePostCommand(post_id=post_id, user_id=1)
        result1 = service.like_post(like_command)

        # いいねが追加されていることを確認
        post = post_repository.find_by_id(post_id)
        assert post.is_liked_by_user(UserId(1))
        assert post.get_like_count() == 1
        assert result1.success is True

        # 2回目いいね（トグルで解除）
        result2 = service.like_post(like_command)

        # いいねが解除されていることを確認
        post = post_repository.find_by_id(post_id)
        assert not post.is_liked_by_user(UserId(1))
        assert post.get_like_count() == 0
        assert result2.success is True

        # 3回目いいね（再び追加）
        result3 = service.like_post(like_command)

        # いいねが再び追加されていることを確認
        post = post_repository.find_by_id(post_id)
        assert post.is_liked_by_user(UserId(1))
        assert post.get_like_count() == 1
        assert result3.success is True

    def test_create_post_events_published(self, setup_service):
        """ポスト作成時のイベント発行テスト"""
        service, _, _, event_publisher, _ = setup_service

        # イベントクリア
        event_publisher.clear_events()

        command = CreatePostCommand(
            user_id=1,
            content="Hello #world @user1",
            visibility=PostVisibility.PUBLIC
        )
        result = service.create_post(command)

        # イベントが発行されていることを確認
        events = event_publisher.get_published_events()
        # eventsがネストされたリストの場合、フラット化
        if events and isinstance(events[0], list):
            events = [event for sublist in events for event in sublist]

        assert len(events) >= 2  # 作成イベント + メンションイベント

        # SnsPostCreatedEventが発行されている
        created_events = [e for e in events if isinstance(e, SnsPostCreatedEvent)]
        assert len(created_events) == 1
        assert created_events[0].aggregate_id.value == result.data["post_id"]
        assert created_events[0].author_user_id.value == 1

        # SnsContentMentionedEventが発行されている（@user1があるため）
        mentioned_events = [e for e in events if isinstance(e, SnsContentMentionedEvent)]
        assert len(mentioned_events) == 1
        assert "user1" in mentioned_events[0].mentioned_user_names

    def test_like_post_events_published(self, setup_service):
        """いいね時のイベント発行テスト"""
        service, _, _, event_publisher, _ = setup_service

        # ポスト作成
        create_command = CreatePostCommand(user_id=1, content="test", visibility=PostVisibility.PUBLIC)
        create_result = service.create_post(create_command)
        post_id = create_result.data["post_id"]

        # イベントクリア
        event_publisher.clear_events()

        # いいね実行
        like_command = LikePostCommand(post_id=post_id, user_id=2)
        service.like_post(like_command)

        # いいねイベントが発行されていることを確認
        events = event_publisher.get_published_events()
        # eventsがネストされたリストの場合、フラット化
        if events and isinstance(events[0], list):
            events = [event for sublist in events for event in sublist]

        assert len(events) >= 1  # 少なくともいいねイベントが発行されている

        # いいねイベントを取得
        liked_events = [e for e in events if isinstance(e, SnsContentLikedEvent)]
        assert len(liked_events) >= 1

        event = liked_events[0]
        assert event.aggregate_id.value == post_id
        assert event.user_id.value == 2
        assert event.content_author_id.value == 1

    def test_delete_post_events_published(self, setup_service):
        """削除時のイベント発行テスト"""
        service, _, _, event_publisher, _ = setup_service

        # ポスト作成
        create_command = CreatePostCommand(user_id=1, content="test", visibility=PostVisibility.PUBLIC)
        create_result = service.create_post(create_command)
        post_id = create_result.data["post_id"]

        # イベントクリア
        event_publisher.clear_events()

        # 削除実行
        delete_command = DeletePostCommand(post_id=post_id, user_id=1)
        service.delete_post(delete_command)

        # 削除イベントが発行されていることを確認
        events = event_publisher.get_published_events()
        # eventsがネストされたリストの場合、フラット化
        if events and isinstance(events[0], list):
            events = [event for sublist in events for event in sublist]

        assert len(events) >= 1  # 少なくとも削除イベントが発行されている

        # 削除イベントを取得
        deleted_events = [e for e in events if isinstance(e, SnsContentDeletedEvent)]
        assert len(deleted_events) >= 1

        event = deleted_events[0]
        assert event.aggregate_id.value == post_id
        assert event.author_user_id.value == 1

    def test_hashtags_extracted_correctly(self, setup_service):
        """ハッシュタグ抽出のテスト"""
        service, post_repository, _, _, _ = setup_service

        command = CreatePostCommand(
            user_id=1,
            content="Hello #world #test #hashtag123 and #日本語タグ",
            visibility=PostVisibility.PUBLIC
        )
        result = service.create_post(command)

        # ハッシュタグが正しく抽出されていることを確認
        post = post_repository.find_by_id(result.data["post_id"])
        hashtags = list(post.post_content.hashtags)

        assert "world" in hashtags
        assert "test" in hashtags
        assert "hashtag123" in hashtags
        assert "日本語タグ" in hashtags
        assert len(hashtags) == 4

    def test_hashtags_case_sensitive(self, setup_service):
        """ハッシュタグの大文字小文字の扱いのテスト"""
        service, post_repository, _, _, _ = setup_service

        command = CreatePostCommand(
            user_id=1,
            content="#Test #test #TEST",
            visibility=PostVisibility.PUBLIC
        )
        result = service.create_post(command)

        # ハッシュタグが大文字小文字を区別して抽出されることを確認
        post = post_repository.find_by_id(result.data["post_id"])
        hashtags = list(post.post_content.hashtags)

        assert "Test" in hashtags
        assert "test" in hashtags
        assert "TEST" in hashtags
        assert len(hashtags) == 3

    def test_no_hashtags_extracted(self, setup_service):
        """ハッシュタグなしの場合のテスト"""
        service, post_repository, _, _, _ = setup_service

        command = CreatePostCommand(
            user_id=1,
            content="Hello world without any hashtags",
            visibility=PostVisibility.PUBLIC
        )
        result = service.create_post(command)

        # ハッシュタグが空であることを確認
        post = post_repository.find_by_id(result.data["post_id"])
        hashtags = list(post.post_content.hashtags)

        assert len(hashtags) == 0

    def test_logging_success_operations(self, setup_service, caplog):
        """成功時のログ出力テスト"""
        service, _, _, _, _ = setup_service

        with caplog.at_level(logging.INFO):
            # ポスト作成
            create_command = CreatePostCommand(user_id=1, content="test", visibility=PostVisibility.PUBLIC)
            result = service.create_post(create_command)

            # ログが正しく出力されていることを確認
            assert "Post created successfully" in caplog.text
            assert str(result.data["post_id"]) in caplog.text

        caplog.clear()

        with caplog.at_level(logging.INFO):
            # いいね
            like_command = LikePostCommand(post_id=result.data["post_id"], user_id=2)
            service.like_post(like_command)

            # ログが正しく出力されていることを確認
            assert "Post liked successfully" in caplog.text

        caplog.clear()

        with caplog.at_level(logging.INFO):
            # 削除
            delete_command = DeletePostCommand(post_id=result.data["post_id"], user_id=1)
            service.delete_post(delete_command)

            # ログが正しく出力されていることを確認
            assert "Post deleted successfully" in caplog.text

    def test_logging_error_operations(self, setup_service):
        """エラー時のログ出力テスト"""
        service, _, _, _, _ = setup_service

        # 予期せぬ例外のログテスト - ログメソッドが呼ばれることを確認
        with patch.object(service._logger, 'error') as mock_error:
            with patch.object(service._post_repository, 'save', side_effect=Exception("Unexpected")):
                create_command = CreatePostCommand(user_id=1, content="test", visibility=PostVisibility.PUBLIC)
                try:
                    service.create_post(create_command)
                except SystemErrorException:
                    pass

                # errorログが呼ばれたことを確認
                mock_error.assert_called()
                call_args = mock_error.call_args[0]
                assert "Unexpected error in create_post:" in call_args[0]

    def test_transaction_rollback_on_failure(self, setup_service):
        """トランザクション失敗時のロールバックテスト"""
        service, post_repository, user_repository, event_publisher, unit_of_work = setup_service

        # ポスト作成前にリポジトリの状態を保存
        initial_post_count = len(post_repository._posts)

        # 存在しないユーザーIDでポストを作成（失敗するはず）
        command = CreatePostCommand(
            user_id=999,  # 存在しないユーザー
            content="テストポスト",
            visibility=PostVisibility.PUBLIC
        )

        # 例外が発生することを確認
        from src.application.social.exceptions.query.user_query_exception import UserQueryException
        with pytest.raises(UserQueryException):
            service.create_post(command)

        # ポストが作成されていないことを確認（ロールバックされた）
        assert len(post_repository._posts) == initial_post_count

        # Unit of Workがロールバックされたことを確認
        assert unit_of_work.is_committed() is False
        assert unit_of_work.is_in_transaction() is False
