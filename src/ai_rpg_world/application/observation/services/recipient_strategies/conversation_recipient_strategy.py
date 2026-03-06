"""会話イベントの観測配信先解決戦略"""

from typing import Any, List

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationEndedEvent,
    ConversationStartedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ConversationRecipientStrategy(IRecipientResolutionStrategy):
    """会話開始・終了の配信先（話し手本人のみ）を返す。"""

    def supports(self, event: Any) -> bool:
        return isinstance(event, (ConversationStartedEvent, ConversationEndedEvent))

    def resolve(self, event: Any) -> List[PlayerId]:
        if isinstance(event, (ConversationStartedEvent, ConversationEndedEvent)):
            return [event.aggregate_id]
        return []

