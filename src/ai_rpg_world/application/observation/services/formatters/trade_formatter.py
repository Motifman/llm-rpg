"""取引イベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)


class TradeObservationFormatter:
    """TradeOfferedEvent / TradeAcceptedEvent / TradeCancelledEvent / TradeDeclinedEvent を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, TradeOfferedEvent):
            return self._format_trade_offered(event, recipient_player_id)
        if isinstance(event, TradeAcceptedEvent):
            return self._format_trade_accepted(event, recipient_player_id)
        if isinstance(event, TradeCancelledEvent):
            return self._format_trade_cancelled(event, recipient_player_id)
        if isinstance(event, TradeDeclinedEvent):
            return self._format_trade_declined(event, recipient_player_id)
        return None

    def _format_trade_offered(
        self, event: TradeOfferedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.offered_item_id)
        trade_id = event.aggregate_id.value
        is_seller = event.seller_id.value == recipient_id.value
        if is_seller:
            prose = f"アイテム「{item_name}」を{event.requested_gold.value}Gで出品しました。"
            structured = {
                "type": "trade_offered",
                "role": "seller",
                "trade_id_value": trade_id,
                "item_name": item_name,
                "requested_gold": event.requested_gold.value,
            }
            return ObservationOutput(
                prose=prose,
                structured=structured,
                observation_category="self_only",
                schedules_turn=True,
            )
        seller_name = self._context.name_resolver.player_name(event.seller_id)
        prose = f"{seller_name}から「{item_name}」の取引提案が届きました（{event.requested_gold.value}G）。"
        structured = {
            "type": "trade_offered",
            "role": "recipient",
            "trade_id_value": trade_id,
            "seller": seller_name,
            "item_name": item_name,
            "requested_gold": event.requested_gold.value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_trade_accepted(
        self, event: TradeAcceptedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        trade_id = event.aggregate_id.value
        is_buyer = event.buyer_id.value == recipient_id.value
        if is_buyer:
            prose = "取引を受諾して購入しました。"
            structured = {
                "type": "trade_accepted",
                "role": "buyer",
                "trade_id_value": trade_id,
            }
        else:
            prose = "取引が受諾されました。"
            structured = {
                "type": "trade_accepted",
                "role": "seller",
                "trade_id_value": trade_id,
                "buyer_player_id": event.buyer_id.value,
            }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_trade_cancelled(
        self, event: TradeCancelledEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        trade_id = event.aggregate_id.value
        prose = "取引がキャンセルされました。"
        structured = {"type": "trade_cancelled", "trade_id_value": trade_id}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_trade_declined(
        self, event: TradeDeclinedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        trade_id = event.aggregate_id.value
        is_decliner = event.decliner_id.value == recipient_id.value
        if is_decliner:
            prose = "取引を断りました。"
            structured = {
                "type": "trade_declined",
                "role": "decliner",
                "trade_id_value": trade_id,
            }
        else:
            decliner_name = self._context.name_resolver.player_name(event.decliner_id)
            prose = f"{decliner_name}が取引を断りました。"
            structured = {
                "type": "trade_declined",
                "role": "seller",
                "trade_id_value": trade_id,
                "decliner_player_id": event.decliner_id.value,
            }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )
