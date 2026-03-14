"""SNS イベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.sns.event import (
    SnsContentLikedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
)


class SnsObservationFormatter:
    """SnsPostCreatedEvent / SnsReplyCreatedEvent / SnsContentLikedEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, SnsPostCreatedEvent):
            return self._format_sns_post_created(event, recipient_player_id)
        if isinstance(event, SnsReplyCreatedEvent):
            return self._format_sns_reply_created(event, recipient_player_id)
        if isinstance(event, SnsContentLikedEvent):
            return self._format_sns_content_liked(event, recipient_player_id)
        if isinstance(event, SnsUserFollowedEvent):
            return self._format_sns_user_followed(event, recipient_player_id)
        if isinstance(event, SnsUserSubscribedEvent):
            return self._format_sns_user_subscribed(event, recipient_player_id)
        return None

    def _sns_user_name(self, user_id: Any) -> str:
        return self._context.name_resolver.sns_user_display_name(user_id)

    def _format_sns_post_created(
        self, event: SnsPostCreatedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        author_name = self._sns_user_name(event.author_user_id)
        content_preview = event.content.content[:50] + (
            "..." if len(event.content.content) > 50 else ""
        )
        post_id_value = event.post_id.value
        prose = f"{author_name}が投稿しました: {content_preview}"
        structured = {
            "type": "sns_post_created",
            "post_id_value": post_id_value,
            "author_name": author_name,
            "content_preview": content_preview,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_sns_reply_created(
        self, event: SnsReplyCreatedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        author_name = self._sns_user_name(event.author_user_id)
        content_preview = event.content.content[:50] + (
            "..." if len(event.content.content) > 50 else ""
        )
        reply_id_value = event.reply_id.value
        parent_post_id_value = event.parent_post_id.value if event.parent_post_id else None
        parent_reply_id_value = (
            event.parent_reply_id.value if event.parent_reply_id else None
        )
        prose = f"{author_name}がリプライしました: {content_preview}"
        structured = {
            "type": "sns_reply_created",
            "reply_id_value": reply_id_value,
            "parent_post_id_value": parent_post_id_value,
            "parent_reply_id_value": parent_reply_id_value,
            "author_name": author_name,
            "content_preview": content_preview,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_sns_content_liked(
        self, event: SnsContentLikedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        liker_name = self._sns_user_name(event.user_id)
        author_name = self._sns_user_name(event.content_author_id)
        target_id_value = event.target_id.value
        prose = f"{liker_name}が{author_name}の{event.content_type}にいいねしました。"
        structured = {
            "type": "sns_content_liked",
            "target_id_value": target_id_value,
            "liker_name": liker_name,
            "content_author_name": author_name,
            "content_type": event.content_type,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_sns_user_followed(
        self, event: SnsUserFollowedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        follower_name = self._sns_user_name(event.follower_user_id)
        followee_name = self._sns_user_name(event.followee_user_id)
        prose = f"{follower_name}が{followee_name}をフォローしました。"
        structured = {
            "type": "sns_user_followed",
            "follower_name": follower_name,
            "followee_name": followee_name,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_sns_user_subscribed(
        self, event: SnsUserSubscribedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        subscriber_name = self._sns_user_name(event.subscriber_user_id)
        subscribed_name = self._sns_user_name(event.subscribed_user_id)
        prose = f"{subscriber_name}が{subscribed_name}をサブスクライブしました。"
        structured = {
            "type": "sns_user_subscribed",
            "subscriber_name": subscriber_name,
            "subscribed_name": subscribed_name,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
            breaks_movement=False,
        )
