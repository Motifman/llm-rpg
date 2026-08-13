"""SQLite取引outbox workerの合成境界。"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from ai_rpg_world.application.common.outbox_worker import (
    DurableEventHandoffPort,
    OutboxWorker,
)
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)
from ai_rpg_world.infrastructure.events.outbox_event_codec_registry import (
    OutboxEventCodecRegistry,
)
from ai_rpg_world.infrastructure.events.sqlite_outbox_delivery_store import (
    SqliteOutboxDeliveryStore,
)
from ai_rpg_world.infrastructure.events.trade_event_json_serializer import (
    TradeEventJsonSerializer,
)


def build_trade_outbox_worker(
    database: Union[str, Path],
    handoff: DurableEventHandoffPort,
) -> OutboxWorker:
    """4種の取引イベントだけを復元・再配送するworkerを作る。"""
    serializer = TradeEventJsonSerializer()
    registry = OutboxEventCodecRegistry()
    for event_type in (
        TradeOfferedEvent,
        TradeAcceptedEvent,
        TradeCancelledEvent,
        TradeDeclinedEvent,
    ):
        registry.register(event_type, serializer)
    return OutboxWorker(
        SqliteOutboxDeliveryStore(database),
        registry,
        handoff,
    )


__all__ = ["build_trade_outbox_worker"]
