from ai_rpg_world.application.common.event_delivery import (
    CommandEventHandlerRegistrarPort,
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.social.services.notification_event_handler_service import NotificationEventHandlerService
from ai_rpg_world.application.social.services.relationship_event_handler_service import RelationshipEventHandlerService
from ai_rpg_world.domain.sns.event import (
    SnsContentLikedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserBlockedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
)


class SnsEventHandlerRegistry:
    """SNSイベントハンドラの登録"""

    def __init__(
        self,
        notification_event_handler: NotificationEventHandlerService,
        relationship_event_handler: RelationshipEventHandlerService,
    ):
        self._notification_event_handler = notification_event_handler
        self._relationship_event_handler = relationship_event_handler

    def register_command_handlers(self, registrar: CommandEventHandlerRegistrarPort) -> None:
        """既存のイベント対応を、確定の前後を保って共通基盤へ登録する。"""
        registrar.register_after_commit(
            SnsUserSubscribedEvent,
            self._notification_event_handler.handle_user_subscribed,
            channel=DeliveryChannel.INTEGRATION,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsUserFollowedEvent,
            self._notification_event_handler.handle_user_followed,
            channel=DeliveryChannel.INTEGRATION,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsPostCreatedEvent,
            self._notification_event_handler.handle_post_created,
            channel=DeliveryChannel.INTEGRATION,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsReplyCreatedEvent,
            self._notification_event_handler.handle_reply_created,
            channel=DeliveryChannel.INTEGRATION,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsContentLikedEvent,
            self._notification_event_handler.handle_content_liked,
            channel=DeliveryChannel.INTEGRATION,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            SnsUserBlockedEvent,
            self._relationship_event_handler.handle_user_blocked,
            channel=DeliveryChannel.INTEGRATION,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
