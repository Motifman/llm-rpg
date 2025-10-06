import logging
from typing import List, Callable, Any, TYPE_CHECKING

from src.application.social.contracts.dtos import NotificationDto
from src.domain.sns.value_object.user_id import UserId
from src.application.social.exceptions import ApplicationException
from src.application.social.exceptions import ApplicationExceptionFactory
from src.application.social.exceptions import SystemErrorException
from src.domain.sns.exception import SnsDomainException

if TYPE_CHECKING:
    from src.domain.sns.repository.sns_notification_repository import SnsNotificationRepository


class NotificationQueryService:
    """通知クエリサービス"""

    def __init__(self, notification_repository: "SnsNotificationRepository"):
        self._notification_repository = notification_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except ApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except SnsDomainException as e:
            raise ApplicationExceptionFactory.create_from_domain_exception(
                e,
                user_id=context.get('user_id'),
                **{k: v for k, v in context.items() if k in ['notification_id']}
            )
        except Exception as e:
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra=context)
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)

    def get_user_notifications(self, user_id: int, limit: int = 50, offset: int = 0) -> List[NotificationDto]:
        """ユーザーの通知一覧を取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_user_notifications_impl(user_id, limit, offset),
            context={
                "action": "get_user_notifications",
                "user_id": user_id,
                "limit": limit,
                "offset": offset
            }
        )

    def _get_user_notifications_impl(self, user_id: int, limit: int = 50, offset: int = 0) -> List[NotificationDto]:
        """ユーザーの通知一覧を取得"""
        user_id_vo = UserId(user_id)
        notifications = self._notification_repository.find_by_user_id(user_id_vo, limit, offset)

        return [
            NotificationDto(
                notification_id=notification.notification_id.value,
                user_id=notification.user_id.value,
                notification_type=notification.notification_type.value,
                title=notification.content.title,
                message=notification.content.message,
                actor_user_id=notification.content.actor_user_id.value,
                actor_user_name=notification.content.actor_user_name,
                related_post_id=notification.content.related_post_id.value if notification.content.related_post_id else None,
                related_reply_id=notification.content.related_reply_id.value if notification.content.related_reply_id else None,
                content_type=notification.content.content_type,
                content_text=notification.content.content_text,
                created_at=notification.created_at,
                is_read=notification.is_read,
                expires_at=notification.expires_at
            )
            for notification in notifications
        ]

    def get_unread_notifications(self, user_id: int) -> List[NotificationDto]:
        """ユーザーの未読通知を取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_unread_notifications_impl(user_id),
            context={
                "action": "get_unread_notifications",
                "user_id": user_id
            }
        )

    def _get_unread_notifications_impl(self, user_id: int) -> List[NotificationDto]:
        """ユーザーの未読通知を取得の実装"""
        user_id_vo = UserId(user_id)
        notifications = self._notification_repository.find_unread_by_user_id(user_id_vo)

        return [
            NotificationDto(
                notification_id=notification.notification_id.value,
                user_id=notification.user_id.value,
                notification_type=notification.notification_type.value,
                title=notification.content.title,
                message=notification.content.message,
                actor_user_id=notification.content.actor_user_id.value,
                actor_user_name=notification.content.actor_user_name,
                related_post_id=notification.content.related_post_id.value if notification.content.related_post_id else None,
                related_reply_id=notification.content.related_reply_id.value if notification.content.related_reply_id else None,
                content_type=notification.content.content_type,
                content_text=notification.content.content_text,
                created_at=notification.created_at,
                is_read=notification.is_read,
                expires_at=notification.expires_at
            )
            for notification in notifications
        ]

    def get_unread_count(self, user_id: int) -> int:
        """未読通知数を取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_unread_count_impl(user_id),
            context={
                "action": "get_unread_count",
                "user_id": user_id
            }
        )

    def _get_unread_count_impl(self, user_id: int) -> int:
        """未読通知数を取得の実装"""
        user_id_vo = UserId(user_id)
        return self._notification_repository.get_unread_count(user_id_vo)
