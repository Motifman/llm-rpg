import logging
from typing import Callable, Any, TYPE_CHECKING

from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.value_object.notification_id import NotificationId
from src.application.sns.contracts.commands import (
    MarkNotificationAsReadCommand,
    MarkAllNotificationsAsReadCommand
)
from src.application.sns.contracts.dtos import CommandResultDto
from src.application.sns.exceptions import ApplicationException
from src.application.sns.exceptions import ApplicationExceptionFactory
from src.application.sns.exceptions import SystemErrorException
from src.domain.sns.exception import SnsDomainException

if TYPE_CHECKING:
    from src.domain.sns.repository.sns_notification_repository import SnsNotificationRepository
    from src.domain.common.unit_of_work import UnitOfWork


class NotificationCommandService:
    """通知コマンドサービス"""

    def __init__(
        self,
        notification_repository: "SnsNotificationRepository",
        unit_of_work: "UnitOfWork"
    ):
        self._notification_repository = notification_repository
        self._unit_of_work = unit_of_work
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

    def mark_notification_as_read(self, command: MarkNotificationAsReadCommand) -> CommandResultDto:
        """通知を既読にする"""
        return self._execute_with_error_handling(
            operation=lambda: self._mark_notification_as_read_impl(command),
            context={
                "action": "mark_notification_as_read",
                "notification_id": command.notification_id
            }
        )

    def _mark_notification_as_read_impl(self, command: MarkNotificationAsReadCommand) -> CommandResultDto:
        """通知を既読にするの実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            notification_id = NotificationId(command.notification_id)
            self._notification_repository.mark_as_read(notification_id)

        self._logger.info(f"Notification marked as read successfully: notification_id={command.notification_id}")

        return CommandResultDto(success=True, message="通知を既読にしました")

    def mark_all_notifications_as_read(self, command: MarkAllNotificationsAsReadCommand) -> CommandResultDto:
        """全通知を既読にする"""
        return self._execute_with_error_handling(
            operation=lambda: self._mark_all_notifications_as_read_impl(command),
            context={
                "action": "mark_all_notifications_as_read",
                "user_id": command.user_id
            }
        )

    def _mark_all_notifications_as_read_impl(self, command: MarkAllNotificationsAsReadCommand) -> CommandResultDto:
        """全通知を既読にするの実装"""
        # トランザクション境界の設定
        with self._unit_of_work:
            user_id = UserId(command.user_id)
            self._notification_repository.mark_all_as_read(user_id)

        self._logger.info(f"All notifications marked as read successfully: user_id={command.user_id}")

        return CommandResultDto(success=True, message="全通知を既読にしました")
