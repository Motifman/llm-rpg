"""クエストイベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    FALLBACK_ITEM_LABEL,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.event.quest_event import (
    QuestAcceptedEvent,
    QuestApprovedEvent,
    QuestCancelledEvent,
    QuestCompletedEvent,
    QuestIssuedEvent,
    QuestPendingApprovalEvent,
)


class QuestObservationFormatter:
    """QuestIssuedEvent / QuestAcceptedEvent / QuestCompletedEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, QuestIssuedEvent):
            return self._format_quest_issued(event, recipient_player_id)
        if isinstance(event, QuestAcceptedEvent):
            return self._format_quest_accepted(event, recipient_player_id)
        if isinstance(event, QuestCompletedEvent):
            return self._format_quest_completed(event, recipient_player_id)
        if isinstance(event, QuestPendingApprovalEvent):
            return self._format_quest_pending_approval(event, recipient_player_id)
        if isinstance(event, QuestApprovedEvent):
            return self._format_quest_approved(event, recipient_player_id)
        if isinstance(event, QuestCancelledEvent):
            return self._format_quest_cancelled(event, recipient_player_id)
        return None

    def _quest_reward_summary(self, reward: Any) -> str:
        """QuestReward を人間可読な文字列に変換する。"""
        gold = getattr(reward, "gold", 0) or 0
        exp = getattr(reward, "exp", 0) or 0
        item_rewards = getattr(reward, "item_rewards", ()) or ()
        parts: list[str] = []
        if gold:
            parts.append(f"{gold}ゴールド")
        if exp:
            parts.append(f"{exp}EXP")
        item_parts: list[str] = []
        for item_spec_id, qty in item_rewards:
            try:
                spec_id_value = int(
                    getattr(item_spec_id, "value", item_spec_id)
                )
            except (TypeError, ValueError):
                item_parts.append(f"{FALLBACK_ITEM_LABEL}を{qty}個")
            else:
                name = self._context.name_resolver.item_spec_name(
                    spec_id_value
                )
                item_parts.append(f"{name}を{qty}個")
        if item_parts:
            parts.append("、".join(item_parts))
        return "、".join(parts) if parts else ""

    def _format_quest_issued(
        self, event: QuestIssuedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        reward_summary = self._quest_reward_summary(event.reward)
        prose = "新しいクエストが発行されました。"
        if reward_summary:
            prose += f" 報酬: {reward_summary}"
        quest_id_value = event.aggregate_id.value
        structured = {
            "type": "quest_issued",
            "quest_id_value": quest_id_value,
            "reward": {"gold": event.reward.gold, "exp": event.reward.exp},
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_quest_accepted(
        self, event: QuestAcceptedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "クエストを受託しました。"
        quest_id_value = event.aggregate_id.value
        structured = {
            "type": "quest_accepted",
            "quest_id_value": quest_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
        )

    def _format_quest_completed(
        self, event: QuestCompletedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        reward_summary = self._quest_reward_summary(event.reward)
        prose = "クエストを完了しました。"
        if reward_summary:
            prose += f" 報酬: {reward_summary}"
        quest_id_value = event.aggregate_id.value
        structured = {
            "type": "quest_completed",
            "quest_id_value": quest_id_value,
            "reward": {
                "gold": event.reward.gold,
                "exp": event.reward.exp,
            },
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_quest_pending_approval(
        self, event: QuestPendingApprovalEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        reward_summary = self._quest_reward_summary(event.reward)
        prose = "クエストが承認待ちになりました。"
        if reward_summary:
            prose += f" 報酬: {reward_summary}"
        quest_id_value = event.aggregate_id.value
        structured = {
            "type": "quest_pending_approval",
            "quest_id_value": quest_id_value,
            "guild_id_value": event.guild_id,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
        )

    def _format_quest_approved(
        self, event: QuestApprovedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        actor = self._context.name_resolver.player_name(event.approved_by)
        prose = f"クエストが承認されました（承認者: {actor}）。"
        quest_id_value = event.aggregate_id.value
        structured = {
            "type": "quest_approved",
            "approved_by": actor,
            "quest_id_value": quest_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
        )

    def _format_quest_cancelled(
        self, event: QuestCancelledEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "クエストがキャンセルされました。"
        quest_id_value = event.aggregate_id.value
        structured = {
            "type": "quest_cancelled",
            "quest_id_value": quest_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
        )
