"""SNS イベントの観測配信先解決戦略"""

from typing import TYPE_CHECKING, Any, List, Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
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

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.repository.sns_user_repository import UserRepository


class SnsRecipientStrategy(IRecipientResolutionStrategy):
    """
    SNS イベントの配信先を解決する。UserId と PlayerId は 1:1 対応を前提とする。

    sns_user_repository が None のときは、メンション・サブスクライバー解決を行わず、
    イベントに直接含まれる著者・親コンテンツ作成者・コンテンツ著者のみを配信先に含める。
    """

    def __init__(self, sns_user_repository: Optional["UserRepository"] = None) -> None:
        self._sns_user_repository = sns_user_repository

    def supports(self, event: Any) -> bool:
        return isinstance(
            event,
            (
                SnsPostCreatedEvent,
                SnsReplyCreatedEvent,
                SnsContentLikedEvent,
                SnsUserFollowedEvent,
                SnsUserSubscribedEvent,
            ),
        )

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

        # メンションされたユーザー
        if self._sns_user_repository is not None and event.mentions:
            for mention in event.mentions:
                user = self._sns_user_repository.find_by_display_name(
                    mention.mentioned_user_name
                )
                if user is not None and user.user_id.value != event.author_user_id.value:
                    result.append(self._to_player_id(user.user_id))

        # サブスクライバー
        if self._sns_user_repository is not None:
            subscriber_ids = self._sns_user_repository.find_subscribers(
                event.author_user_id
            )
            for uid in subscriber_ids:
                if uid.value != event.author_user_id.value:
                    result.append(self._to_player_id(uid))

        return result

    def _resolve_reply_created(self, event: SnsReplyCreatedEvent) -> List[PlayerId]:
        result: List[PlayerId] = []

        # 親コンテンツの作成者
        if event.parent_author_id is not None:
            result.append(self._to_player_id(event.parent_author_id))

        # メンションされたユーザー
        if self._sns_user_repository is not None and event.mentions:
            for mention in event.mentions:
                user = self._sns_user_repository.find_by_display_name(
                    mention.mentioned_user_name
                )
                if user is not None and user.user_id.value != event.author_user_id.value:
                    result.append(self._to_player_id(user.user_id))

        return result
