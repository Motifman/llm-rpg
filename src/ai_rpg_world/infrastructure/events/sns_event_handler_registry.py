from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.common.event_delivery import (
    CommandEventHandlerRegistrarPort,
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.social.services.notification_event_handler_service import NotificationEventHandlerService
from ai_rpg_world.application.social.services.relationship_event_handler_service import RelationshipEventHandlerService
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.sns.event import (
    SnsContentLikedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserBlockedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class SnsEventHandlerRegistry:
    """SNSイベントハンドラの登録"""

    def __init__(
        self,
        notification_event_handler: NotificationEventHandlerService,
        relationship_event_handler: RelationshipEventHandlerService
    ):
        self._notification_event_handler = notification_event_handler
        self._relationship_event_handler = relationship_event_handler

    def register_handlers(self, event_publisher: EventPublisher[DomainEvent]) -> None:
        """全イベントハンドラをEventPublisherに登録"""

        # 通知関連イベントハンドラ
        event_publisher.register_handler(
            SnsUserSubscribedEvent,
            self._create_event_handler(self._notification_event_handler.handle_user_subscribed),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            SnsUserFollowedEvent,
            self._create_event_handler(self._notification_event_handler.handle_user_followed),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            SnsPostCreatedEvent,
            self._create_event_handler(self._notification_event_handler.handle_post_created),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            SnsReplyCreatedEvent,
            self._create_event_handler(self._notification_event_handler.handle_reply_created),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            SnsContentLikedEvent,
            self._create_event_handler(self._notification_event_handler.handle_content_liked),
            is_synchronous=False,
        )

        # 関係管理イベントハンドラ
        event_publisher.register_handler(
            SnsUserBlockedEvent,
            self._create_event_handler(self._relationship_event_handler.handle_user_blocked),
            is_synchronous=False,
        )

    def register_command_handlers(self, registrar: CommandEventHandlerRegistrarPort) -> None:
        """既存のイベント対応を、確定の前後を保って共通基盤へ登録する。"""
        registrar.register_after_commit(
            SnsUserSubscribedEvent, self._notification_event_handler.handle_user_subscribed,
            channel=DeliveryChannel.INTEGRATION, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsUserFollowedEvent, self._notification_event_handler.handle_user_followed,
            channel=DeliveryChannel.INTEGRATION, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsPostCreatedEvent, self._notification_event_handler.handle_post_created,
            channel=DeliveryChannel.INTEGRATION, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsReplyCreatedEvent, self._notification_event_handler.handle_reply_created,
            channel=DeliveryChannel.INTEGRATION, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsContentLikedEvent, self._notification_event_handler.handle_content_liked,
            channel=DeliveryChannel.INTEGRATION, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsUserBlockedEvent, self._relationship_event_handler.handle_user_blocked,
            channel=DeliveryChannel.INTEGRATION, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )

    def _create_event_handler(
        self, handler_method: Callable[[Any], None]
    ) -> "EventHandler[Any]":
        """イベントハンドラオブジェクトを作成"""
        class EventHandlerImpl(EventHandler[Any]):
            def __init__(self, method: Callable[[Any], None]) -> None:
                self._method = method

            def handle(self, event: Any) -> None:
                self._method(event)

        return EventHandlerImpl(handler_method)
