from typing import TYPE_CHECKING
from src.domain.common.event_publisher import EventPublisher
from src.domain.sns.event import (
    SnsUserSubscribedEvent,
    SnsUserFollowedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsContentLikedEvent,
    SnsUserBlockedEvent,
)
from src.application.social.services.notification_event_handler_service import NotificationEventHandlerService
from src.application.social.services.relationship_event_handler_service import RelationshipEventHandlerService

if TYPE_CHECKING:
    from src.domain.common.event_handler import EventHandler


class SnsEventHandlerRegistry:
    """SNSイベントハンドラの登録"""

    def __init__(
        self,
        notification_event_handler: NotificationEventHandlerService,
        relationship_event_handler: RelationshipEventHandlerService
    ):
        self._notification_event_handler = notification_event_handler
        self._relationship_event_handler = relationship_event_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        """全イベントハンドラをEventPublisherに登録"""

        # 通知関連イベントハンドラ
        event_publisher.register_handler(
            SnsUserSubscribedEvent,
            self._create_event_handler(self._notification_event_handler.handle_user_subscribed)
        )
        event_publisher.register_handler(
            SnsUserFollowedEvent,
            self._create_event_handler(self._notification_event_handler.handle_user_followed)
        )
        event_publisher.register_handler(
            SnsPostCreatedEvent,
            self._create_event_handler(self._notification_event_handler.handle_post_created)
        )
        event_publisher.register_handler(
            SnsReplyCreatedEvent,
            self._create_event_handler(self._notification_event_handler.handle_reply_created)
        )
        event_publisher.register_handler(
            SnsContentLikedEvent,
            self._create_event_handler(self._notification_event_handler.handle_content_liked)
        )

        # 関係管理イベントハンドラ
        event_publisher.register_handler(
            SnsUserBlockedEvent,
            self._create_event_handler(self._relationship_event_handler.handle_user_blocked)
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        """イベントハンドラオブジェクトを作成"""
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
