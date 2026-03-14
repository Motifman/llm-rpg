"""会話イベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationEndedEvent,
    ConversationStartedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class ConversationObservationFormatter:
    """ConversationStartedEvent / ConversationEndedEvent を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, ConversationStartedEvent):
            return self._format_conversation_started(event, recipient_player_id)
        if isinstance(event, ConversationEndedEvent):
            return self._format_conversation_ended(event, recipient_player_id)
        return None

    def _format_conversation_started(
        self, event: ConversationStartedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        npc_name = self._context.name_resolver.npc_name(event.npc_id_value)
        prose = f"{npc_name}と会話を始めました。"
        structured = {
            "type": "conversation_started",
            "npc_name": npc_name,
            "world_object_id": event.npc_id_value,
            "npc_id_value": event.npc_id_value,
            "dialogue_tree_id_value": event.dialogue_tree_id_value,
            "entry_node_id_value": event.entry_node_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=True,
        )

    def _format_conversation_ended(
        self, event: ConversationEndedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        npc_name = self._context.name_resolver.npc_name(event.npc_id_value)
        parts: list[str] = [f"{npc_name}との会話を終えました。"]
        if event.outcome:
            parts.append(str(event.outcome))
        if event.rewards_claimed_gold:
            parts.append(f"{event.rewards_claimed_gold}ゴールドを獲得しました。")
        if event.rewards_claimed_items:
            item_parts: list[str] = []
            for spec_id_value, qty in event.rewards_claimed_items:
                name = self._context.name_resolver.item_spec_name(spec_id_value)
                item_parts.append(f"{name}を{qty}個")
            if item_parts:
                parts.append("報酬: " + "、".join(item_parts))
        if event.quest_unlocked_ids:
            parts.append(f"新しいクエストが{len(event.quest_unlocked_ids)}件解放されました。")
        prose = " ".join(parts)
        structured = {
            "type": "conversation_ended",
            "npc_name": npc_name,
            "world_object_id": event.npc_id_value,
            "npc_id_value": event.npc_id_value,
            "end_node_id_value": event.end_node_id_value,
            "outcome": event.outcome,
            "rewards_claimed_gold": event.rewards_claimed_gold,
            "rewards_claimed_items": list(event.rewards_claimed_items),
            "quest_unlocked_count": len(event.quest_unlocked_ids),
            "quest_unlocked_ids": list(event.quest_unlocked_ids),
            "quest_completed_quest_ids": list(event.quest_completed_quest_ids),
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
        )
