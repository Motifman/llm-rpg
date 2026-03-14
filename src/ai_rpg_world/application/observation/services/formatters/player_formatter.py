"""プレイヤーイベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerLocationChangedEvent,
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
    PlayerRevivedEvent,
)
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
)


class PlayerObservationFormatter:
    """PlayerLocationChangedEvent / ItemAddedToInventoryEvent / PlayerSpokeEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, PlayerLocationChangedEvent):
            return self._format_player_location_changed(event, recipient_player_id)
        if isinstance(event, PlayerDownedEvent):
            return self._format_player_downed(event, recipient_player_id)
        if isinstance(event, PlayerRevivedEvent):
            return self._format_player_revived(event, recipient_player_id)
        if isinstance(event, PlayerLevelUpEvent):
            return self._format_player_level_up(event, recipient_player_id)
        if isinstance(event, PlayerGoldEarnedEvent):
            return self._format_player_gold_earned(event, recipient_player_id)
        if isinstance(event, PlayerGoldPaidEvent):
            return self._format_player_gold_paid(event, recipient_player_id)
        if isinstance(event, ItemAddedToInventoryEvent):
            return self._format_item_added_to_inventory(event, recipient_player_id)
        if isinstance(event, ItemDroppedFromInventoryEvent):
            return self._format_item_dropped(event, recipient_player_id)
        if isinstance(event, ItemEquippedEvent):
            return self._format_item_equipped(event, recipient_player_id)
        if isinstance(event, ItemUnequippedEvent):
            return self._format_item_unequipped(event, recipient_player_id)
        if isinstance(event, InventorySlotOverflowEvent):
            return self._format_inventory_slot_overflow(event, recipient_player_id)
        if isinstance(event, PlayerSpokeEvent):
            return self._format_player_spoke(event, recipient_player_id)
        return None

    def _format_player_location_changed(
        self, event: PlayerLocationChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        spot_name = self._context.name_resolver.spot_name(event.new_spot_id)
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = f"現在地: {spot_name}"
            structured = {
                "type": "current_location",
                "spot_name": spot_name,
                "spot_id_value": event.new_spot_id.value,
                "role": "self",
            }
            return ObservationOutput(
                prose=prose, structured=structured, observation_category="self_only"
            )
        actor_name = self._context.name_resolver.player_name(event.aggregate_id)
        prose = f"{actor_name}がこのスポットにやってきました。"
        structured = {
            "type": "player_entered_spot",
            "actor": actor_name,
            "spot_name": spot_name,
            "spot_id_value": event.new_spot_id.value,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_player_downed(
        self, event: PlayerDownedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        killer_name = (
            self._context.name_resolver.player_name(event.killer_player_id)
            if getattr(event, "killer_player_id", None) is not None
            else None
        )
        killer_id = (
            getattr(event.killer_player_id, "value", None)
            if getattr(event, "killer_player_id", None)
            else None
        )
        if is_self:
            prose = "戦闘不能になりました。"
            if killer_name:
                prose = f"{killer_name}に倒されました。"
            structured = {"type": "player_downed", "role": "self", "killer_player_id": killer_id}
            return ObservationOutput(
                prose=prose,
                structured=structured,
                observation_category="self_only",
                schedules_turn=True,
                breaks_movement=True,
            )
        actor_name = self._context.name_resolver.player_name(event.aggregate_id)
        prose = f"{actor_name}が戦闘不能になりました。"
        if killer_name:
            prose = f"{actor_name}が{killer_name}に倒されました。"
        structured = {"type": "player_downed", "actor": actor_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_player_revived(
        self, event: PlayerRevivedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = "復帰しました。"
            structured = {"type": "player_revived", "role": "self"}
            return ObservationOutput(
                prose=prose, structured=structured, observation_category="self_only"
            )
        actor_name = self._context.name_resolver.player_name(event.aggregate_id)
        prose = f"{actor_name}が復帰しました。"
        structured = {"type": "player_revived", "actor": actor_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_player_level_up(
        self, event: PlayerLevelUpEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"レベルが上がりました（{event.old_level} → {event.new_level}）。"
        structured = {"type": "level_up", "old_level": event.old_level, "new_level": event.new_level}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_player_gold_earned(
        self, event: PlayerGoldEarnedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.earned_amount}ゴールドを獲得しました。"
        structured = {"type": "gold_earned", "amount": event.earned_amount}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_player_gold_paid(
        self, event: PlayerGoldPaidEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.paid_amount}ゴールドを支払いました。"
        structured = {"type": "gold_paid", "amount": event.paid_amount}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_player_spoke(
        self, event: PlayerSpokeEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        speaker_name = self._context.name_resolver.player_name(event.aggregate_id)
        if event.channel == SpeechChannel.WHISPER:
            verb = "囁いた"
        elif event.channel == SpeechChannel.SAY:
            verb = "言った"
        else:
            verb = "叫んだ"
        prose = f"{speaker_name}が{verb}: 「{event.content}」"
        is_self = event.aggregate_id.value == recipient_id.value
        structured = {
            "type": "player_spoke",
            "speaker": speaker_name,
            "speaker_player_id": event.aggregate_id.value,
            "channel": event.channel.value,
            "content": event.content,
            "role": "self" if is_self else "other",
        }
        category = "self_only" if is_self else "social"
        return ObservationOutput(
            prose=prose, structured=structured, observation_category=category
        )

    def _format_item_added_to_inventory(
        self, event: ItemAddedToInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        agg = None
        if self._context.item_repository:
            agg = self._context.item_repository.find_by_id(event.item_instance_id)
        qty = agg.quantity if agg is not None else 1
        if qty != 1:
            prose = f"{item_name}を{qty}個入手しました。"
        else:
            prose = f"{item_name}を入手しました。"
        structured = {"type": "item_added_to_inventory", "item_name": item_name}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_item_dropped(
        self, event: ItemDroppedFromInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        prose = f"{item_name}を捨てました。"
        structured = {"type": "item_dropped", "item_name": item_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )

    def _format_item_equipped(
        self, event: ItemEquippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        prose = f"{item_name}を装備しました。"
        structured = {"type": "item_equipped", "item_name": item_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )

    def _format_item_unequipped(
        self, event: ItemUnequippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        prose = f"{item_name}を外しました。"
        structured = {"type": "item_unequipped", "item_name": item_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )

    def _format_inventory_slot_overflow(
        self, event: InventorySlotOverflowEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(
            event.overflowed_item_instance_id
        )
        prose = f"インベントリが満杯で{item_name}が溢れました。"
        structured = {"type": "inventory_overflow", "item_name": item_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )
