"""
NotificationCommandServiceのテスト
"""
import pytest
import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from src.application.social.services.notification_command_service import NotificationCommandService
from src.infrastructure.repository.in_memory_sns_notification_repository_with_uow import InMemorySnsNotificationRepositoryWithUow
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from src.application.social.contracts.commands import (
    MarkNotificationAsReadCommand,
    MarkAllNotificationsAsReadCommand
)
from src.application.social.contracts.dtos import CommandResultDto
from src.application.social.exceptions.command.notification_command_exception import (
    NotificationCommandException,
    NotificationMarkAsReadException,
    NotificationMarkAllAsReadException,
    NotificationNotFoundForCommandException,
    NotificationAccessDeniedException,
)
from src.application.social.exceptions.query.user_query_exception import UserQueryException
from src.application.social.exceptions import SystemErrorException
from src.domain.sns.exception import (
    UserNotFoundException,
    NotificationIdValidationException,
)
from src.domain.sns.value_object import UserId, NotificationId
from src.domain.sns.value_object.notification_content import NotificationContent
from src.domain.sns.value_object.notification_type import NotificationType
from src.domain.sns.entity.notification import Notification


class TestNotificationCommandService:
    """NotificationCommandServiceのテストクラス"""

    @pytest.fixture
    def setup_service(self):
        """テスト用のサービスとリポジトリをセットアップ"""
        # Unit of Workを作成
        unit_of_work = InMemoryUnitOfWork(unit_of_work_factory=lambda: InMemoryUnitOfWork())
        notification_repository = InMemorySnsNotificationRepositoryWithUow(unit_of_work)

        # サービスを作成
        service = NotificationCommandService(notification_repository, unit_of_work)

        # テストデータをセットアップ
        self.setup_test_data(notification_repository)

        return service, notification_repository, unit_of_work

    def setup_test_data(self, notification_repository):
        """テストデータをセットアップ"""
        # 通知データをクリア
        notification_repository.clear()

        # ユーザー1の通知を作成
        notification1 = Notification.create_persistent_notification(
            notification_id=NotificationId(1),
            user_id=UserId(1),
            notification_type=NotificationType.FOLLOW,
            content=NotificationContent.create_follow_notification(
                follower_user_id=UserId(2),
                follower_user_name="ユーザー2"
            )
        )

        notification2 = Notification.create_persistent_notification(
            notification_id=NotificationId(2),
            user_id=UserId(1),
            notification_type=NotificationType.LIKE,
            content=NotificationContent.create_like_notification(
                liker_user_id=UserId(3),
                liker_user_name="ユーザー3",
                content_type="post",
                content_id=1
            )
        )

        # ユーザー2の通知を作成
        notification3 = Notification.create_persistent_notification(
            notification_id=NotificationId(3),
            user_id=UserId(2),
            notification_type=NotificationType.REPLY,
            content=NotificationContent.create_reply_notification(
                replier_user_id=UserId(1),
                replier_user_name="ユーザー1",
                content_type="post",
                content_id=2
            )
        )

        # リポジトリに保存
        notification_repository.save(notification1)
        notification_repository.save(notification2)
        notification_repository.save(notification3)

    def create_test_notification(self, notification_id: int, user_id: int, notification_type: NotificationType, actor_user_id: int, actor_user_name: str) -> Notification:
        """テスト用の通知を作成"""
        if notification_type == NotificationType.FOLLOW:
            content = NotificationContent.create_follow_notification(
                follower_user_id=UserId(actor_user_id),
                follower_user_name=actor_user_name
            )
        elif notification_type == NotificationType.LIKE:
            content = NotificationContent.create_like_notification(
                liker_user_id=UserId(actor_user_id),
                liker_user_name=actor_user_name,
                content_type="post",
                content_id=1
            )
        elif notification_type == NotificationType.REPLY:
            content = NotificationContent.create_reply_notification(
                replier_user_id=UserId(actor_user_id),
                replier_user_name=actor_user_name,
                content_type="post",
                content_id=1
            )
        else:
            content = NotificationContent.create_follow_notification(
                follower_user_id=UserId(actor_user_id),
                follower_user_name=actor_user_name
            )

        return Notification.create_persistent_notification(
            notification_id=NotificationId(notification_id),
            user_id=UserId(user_id),
            notification_type=notification_type,
            content=content
        )

    class TestMarkNotificationAsRead:
        """mark_notification_as_readメソッドのテスト"""

        def test_success_mark_notification_as_read(self, setup_service):
            """正常系: 通知を既読にできる"""
            service, repository, unit_of_work = setup_service

            command = MarkNotificationAsReadCommand(
                notification_id=1
            )

            result = service.mark_notification_as_read(command)

            assert isinstance(result, CommandResultDto)
            assert result.success is True
            assert "既読にしました" in result.message

            # 通知が既読になっていることを確認
            notification = repository.find_by_id(NotificationId(1))
            assert notification.is_read is True

        def test_success_mark_already_read_notification(self, setup_service):
            """正常系: 既に既読の通知を既読にしてもエラーにならない"""
            service, repository, unit_of_work = setup_service

            # まず既読にする
            repository.mark_as_read(NotificationId(1))

            command = MarkNotificationAsReadCommand(
                notification_id=1
            )

            result = service.mark_notification_as_read(command)

            assert result.success is True
            assert "既読にしました" in result.message

        def test_success_notification_not_found(self, setup_service):
            """正常系: 存在しない通知ID（何も起こらない）"""
            service, repository, unit_of_work = setup_service

            command = MarkNotificationAsReadCommand(
                notification_id=999
            )

            # 存在しない通知IDの場合は何も起こらない（正常動作）
            result = service.mark_notification_as_read(command)

            assert isinstance(result, CommandResultDto)
            assert result.success is True

        def test_error_invalid_notification_id(self, setup_service):
            """異常系: 無効な通知ID"""
            service, repository, unit_of_work = setup_service

            command = MarkNotificationAsReadCommand(
                notification_id=0
            )

            with pytest.raises(NotificationCommandException):
                service.mark_notification_as_read(command)


    class TestMarkAllNotificationsAsRead:
        """mark_all_notifications_as_readメソッドのテスト"""

        def test_success_mark_all_notifications_as_read(self, setup_service):
            """正常系: 全通知を既読にできる"""
            service, repository, unit_of_work = setup_service

            command = MarkAllNotificationsAsReadCommand(user_id=1)

            result = service.mark_all_notifications_as_read(command)

            assert isinstance(result, CommandResultDto)
            assert result.success is True
            assert "全通知を既読にしました" in result.message

            # ユーザー1の通知がすべて既読になっていることを確認
            unread_count = repository.get_unread_count(UserId(1))
            assert unread_count == 0

            # ユーザー2の通知は変更されていないことを確認
            unread_count_user2 = repository.get_unread_count(UserId(2))
            assert unread_count_user2 == 1  # もともと1件あった

        def test_success_no_notifications_to_mark(self, setup_service):
            """正常系: 通知がないユーザーの場合"""
            service, repository, unit_of_work = setup_service

            command = MarkAllNotificationsAsReadCommand(user_id=999)

            result = service.mark_all_notifications_as_read(command)

            assert result.success is True
            assert "全通知を既読にしました" in result.message

        def test_error_invalid_user_id(self, setup_service):
            """異常系: 無効なユーザーID"""
            service, repository, unit_of_work = setup_service

            command = MarkAllNotificationsAsReadCommand(user_id=0)

            with pytest.raises(UserQueryException):
                service.mark_all_notifications_as_read(command)

    class TestExceptionHandling:
        """例外処理のテスト"""

        def test_domain_exception_handling(self, setup_service):
            """ドメイン例外が適切にアプリケーション例外に変換される"""
            service, repository, unit_of_work = setup_service

            command = MarkNotificationAsReadCommand(
                notification_id=-1  # 無効な通知ID
            )

            with pytest.raises(NotificationCommandException):
                service.mark_notification_as_read(command)

        def test_unexpected_error_handling(self, setup_service):
            """予期せぬエラーがSystemErrorExceptionに変換される"""
            service, repository, unit_of_work = setup_service

            # リポジトリのmark_as_readをモックして例外を投げるようにする
            with patch.object(repository, 'mark_as_read', side_effect=RuntimeError("Database connection failed")):
                command = MarkNotificationAsReadCommand(
                    notification_id=1
                )

                with pytest.raises(SystemErrorException):
                    service.mark_notification_as_read(command)

    class TestLogging:
        """ロギングのテスト"""

        def test_success_logging(self, setup_service, caplog):
            """正常系の操作で適切なログが出力される"""
            service, repository, unit_of_work = setup_service

            with caplog.at_level(logging.INFO):
                command = MarkNotificationAsReadCommand(
                    notification_id=1
                )
                service.mark_notification_as_read(command)

            # INFOレベルのログが含まれていることを確認
            assert any("Notification marked as read successfully" in record.message
                      for record in caplog.records)

        def test_all_notifications_logging(self, setup_service, caplog):
            """全通知既読で適切なログが出力される"""
            service, repository, unit_of_work = setup_service

            with caplog.at_level(logging.INFO):
                command = MarkAllNotificationsAsReadCommand(user_id=1)
                service.mark_all_notifications_as_read(command)

            # INFOレベルのログが含まれていることを確認
            assert any("All notifications marked as read successfully" in record.message
                      for record in caplog.records)
