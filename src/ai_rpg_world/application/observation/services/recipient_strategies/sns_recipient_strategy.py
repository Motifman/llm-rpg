"""SNS イベントの観測配信先解決戦略"""

from typing import Any, List

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.sns.event import (
    SnsContentLikedEvent,
    SnsPostCreatedEvent,
    SnsReplyCreatedEvent,
    SnsUserFollowedEvent,
    SnsUserSubscribedEvent,
)
from ai_rpg_world.domain.sns.value_object.user_id import UserId


class SnsRecipientStrategy(IRecipientResolutionStrategy):
    """
    SNS イベントの配信先を解決する。UserId と PlayerId は 1:1 対応を前提とする。

    ポスト・リプライ作成はイベント上の mentioned_user_ids / subscriber_user_ids で完結する。
    """

    _STRATEGY_KEY = "sns"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
    ) -> None:
        self._registry = observed_event_registry

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def _to_player_id(self, user_id: UserId) -> PlayerId:
        """UserId を PlayerId に変換（1:1 対応）。"""
        return PlayerId(user_id.value)

    def resolve(self, event: Any) -> List[PlayerId]:
        if isinstance(event, SnsPostCreatedEvent):
            return self._resolve_post_created(event)
        if isinstance(event, SnsReplyCreatedEvent):
            return self._resolve_reply_created(event)
        if isinstance(event, SnsContentLikedEvent):
            return [self._to_player_id(event.content_author_id)]
        if isinstance(event, SnsUserFollowedEvent):
            return [self._to_player_id(event.followee_user_id)]
        if isinstance(event, SnsUserSubscribedEvent):
            return [self._to_player_id(event.subscribed_user_id)]
        return []

    def _resolve_post_created(self, event: SnsPostCreatedEvent) -> List[PlayerId]:
        result: List[PlayerId] = [self._to_player_id(event.author_user_id)]

        for uid in event.mentioned_user_ids:
            if uid.value != event.author_user_id.value:
                result.append(self._to_player_id(uid))

        for uid in event.subscriber_user_ids:
            if uid.value != event.author_user_id.value:
                result.append(self._to_player_id(uid))

        return result

    def _resolve_reply_created(self, event: SnsReplyCreatedEvent) -> List[PlayerId]:
        result: List[PlayerId] = []

        if event.parent_author_id is not None:
            result.append(self._to_player_id(event.parent_author_id))

        for uid in event.mentioned_user_ids:
            if uid.value != event.author_user_id.value:
                result.append(self._to_player_id(uid))

        return result
