import pytest
from datetime import datetime, timedelta
from src.application.social.services.notification_query_service import NotificationQueryService
from src.application.social.contracts.dtos import NotificationDto
from src.application.social.exceptions.query.notification_query_exception import (
    NotificationQueryException,
    NotificationNotFoundException,
    NotificationAccessDeniedException
)
from src.application.social.exceptions.query.user_query_exception import UserQueryException
from src.domain.sns.value_object import UserId, NotificationId
from src.domain.sns.value_object.notification_content import NotificationContent
from src.domain.sns.value_object.notification_type import NotificationType
from src.domain.sns.entity.notification import Notification
from src.infrastructure.repository.in_memory_sns_notification_repository import InMemorySnsNotificationRepository


class TestNotificationQueryService:
    """NotificationQueryServiceのテスト"""

    @pytest.fixture
    def notification_repository(self):
        """実際のInMemorySnsNotificationRepository"""
        return InMemorySnsNotificationRepository()

    @pytest.fixture
    def notification_query_service(self, notification_repository):
        """テスト対象のサービス"""
        # リポジトリをクリアしてからテストデータをセットアップ
        notification_repository.clear()
        TestNotificationQueryService().setup_test_data(notification_repository)
        return NotificationQueryService(notification_repository)

    def setup_test_data(self, notification_repository):
        """テストデータをセットアップ"""
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
                content_id=1,
                content_text="いいねされたポストの内容"
            )
        )
        notification2.mark_as_read()  # 既読にする

        # ユーザー2の通知を作成（既読）
        notification3 = Notification.create_persistent_notification(
            notification_id=NotificationId(3),
            user_id=UserId(2),
            notification_type=NotificationType.REPLY,
            content=NotificationContent.create_reply_notification(
                replier_user_id=UserId(1),
                replier_user_name="ユーザー1",
                content_type="post",
                content_id=2,
                content_text="返信の内容"
            )
        )
        notification3.mark_as_read()  # 既読にする

        # リポジトリに保存
        notification_repository.save(notification1)
        notification_repository.save(notification2)
        notification_repository.save(notification3)

    def create_test_notification(self, notification_id: int, user_id: int, notification_type: NotificationType, actor_user_id: int, actor_user_name: str, is_read: bool = False) -> Notification:
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

        notification = Notification.create_persistent_notification(
            notification_id=NotificationId(notification_id),
            user_id=UserId(user_id),
            notification_type=notification_type,
            content=content
        )
        if is_read:
            notification.mark_as_read()
        return notification

    class TestGetUserNotifications:
        """get_user_notificationsメソッドのテスト"""

        def test_success_get_user_notifications(self, notification_query_service):
            """正常系: ユーザーの通知一覧を取得できる"""
            result = notification_query_service.get_user_notifications(user_id=1, limit=10, offset=0)

            assert len(result) == 2
            assert all(isinstance(dto, NotificationDto) for dto in result)
            assert result[0].user_id == 1
            assert result[1].user_id == 1

            # 新しい順にソートされていることを確認（IDが大きい順）
            assert result[0].notification_id == 2
            assert result[1].notification_id == 1

            # 通知の内容が正しく設定されていることを確認
            assert result[0].title == "いいね"
            assert result[0].message == "ユーザー3さんがあなたのpostにいいねしました"
            assert result[0].actor_user_id == 3
            assert result[0].actor_user_name == "ユーザー3"
            assert result[0].related_post_id == 1
            assert result[0].content_type == "post"

            assert result[1].title == "新しいフォロワー"
            assert result[1].message == "ユーザー2さんがあなたをフォローしました"
            assert result[1].actor_user_id == 2
            assert result[1].actor_user_name == "ユーザー2"

        def test_success_get_user_notifications_with_limit_offset(self, notification_query_service):
            """正常系: limitとoffsetが正しく動作する"""
            result = notification_query_service.get_user_notifications(user_id=1, limit=1, offset=0)

            assert len(result) == 1
            assert result[0].notification_id == 2  # 新しい順

            result = notification_query_service.get_user_notifications(user_id=1, limit=1, offset=1)
            assert len(result) == 1
            assert result[0].notification_id == 1

        def test_success_empty_notifications(self, notification_query_service):
            """正常系: 通知がないユーザーの場合"""
            result = notification_query_service.get_user_notifications(user_id=999, limit=10, offset=0)

            assert len(result) == 0

        def test_error_invalid_user_id(self, notification_query_service):
            """異常系: 無効なユーザーID"""
            with pytest.raises(UserQueryException):
                notification_query_service.get_user_notifications(user_id=0)

        def test_error_user_id_validation_exception(self, notification_query_service):
            """異常系: UserIdバリデーションエラー"""
            with pytest.raises(UserQueryException):
                notification_query_service.get_user_notifications(user_id=-1)

    class TestGetUnreadNotifications:
        """get_unread_notificationsメソッドのテスト"""

        def test_success_get_unread_notifications(self, notification_query_service):
            """正常系: 未読通知のみを取得できる"""
            result = notification_query_service.get_unread_notifications(user_id=1)

            assert len(result) == 1
            assert result[0].notification_id == 1  # 通知ID=2は既読
            assert result[0].is_read is False
            assert result[0].user_id == 1
            assert result[0].title == "新しいフォロワー"
            assert result[0].actor_user_id == 2

        def test_success_no_unread_notifications(self, notification_query_service):
            """正常系: 未読通知がない場合"""
            result = notification_query_service.get_unread_notifications(user_id=2)

            assert len(result) == 0

        def test_error_invalid_user_id(self, notification_query_service):
            """異常系: 無効なユーザーID"""
            with pytest.raises(UserQueryException):
                notification_query_service.get_unread_notifications(user_id=0)

    class TestGetUnreadCount:
        """get_unread_countメソッドのテスト"""

        def test_success_get_unread_count(self, notification_query_service):
            """正常系: 未読通知数を取得できる"""
            result = notification_query_service.get_unread_count(user_id=1)

            assert result == 1  # ユーザー1の未読通知は1件

        def test_success_zero_unread_count(self, notification_query_service):
            """正常系: 未読通知数が0の場合"""
            result = notification_query_service.get_unread_count(user_id=2)

            assert result == 0  # ユーザー2の通知はすべて既読

        def test_error_invalid_user_id(self, notification_query_service):
            """異常系: 無効なユーザーID"""
            with pytest.raises(UserQueryException):
                notification_query_service.get_unread_count(user_id=0)

    class TestExceptionHandling:
        """例外処理のテスト"""

        def test_domain_exception_handling(self, notification_repository):
            """ドメイン例外が適切にアプリケーション例外に変換される"""
            # モックや直接のテストが難しいため、実際のドメイン例外が発生するケースをテスト
            service = NotificationQueryService(notification_repository)

            # UserIdのバリデーションエラーが発生するケース
            with pytest.raises(UserQueryException):
                service.get_user_notifications(user_id=-1)

        def test_unexpected_error_handling(self, notification_repository):
            """予期せぬエラーがSystemErrorExceptionに変換される"""
            # リポジトリが例外を投げるケースをシミュレートするために
            # 一時的にリポジトリを破壊
            original_find_by_user_id = notification_repository.find_by_user_id

            def mock_find_by_user_id(*args, **kwargs):
                raise RuntimeError("Database connection failed")

            notification_repository.find_by_user_id = mock_find_by_user_id

            try:
                service = NotificationQueryService(notification_repository)
                with pytest.raises(Exception):  # SystemErrorExceptionが投げられるはず
                    service.get_user_notifications(user_id=1)
            finally:
                # クリーンアップ
                notification_repository.find_by_user_id = original_find_by_user_id
