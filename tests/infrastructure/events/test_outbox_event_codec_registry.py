"""OutboxEventCodecRegistryが許可型とschemaを厳密に解決することを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.common.outbox_worker import (
    PermanentOutboxMessageException,
    StoredOutboxMessage,
)
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)
from ai_rpg_world.infrastructure.events.outbox_event_codec_registry import (
    OutboxEventCodecRegistry,
    event_type_name,
)
from ai_rpg_world.infrastructure.events.trade_event_json_serializer import (
    TradeEventJsonSerializer,
)
from tests.infrastructure.events.test_trade_event_json_serializer import _events


def _registry() -> OutboxEventCodecRegistry:
    registry = OutboxEventCodecRegistry()
    serializer = TradeEventJsonSerializer()
    for event_type in (
        TradeOfferedEvent,
        TradeAcceptedEvent,
        TradeCancelledEvent,
        TradeDeclinedEvent,
    ):
        registry.register(event_type, serializer)
    return registry


@pytest.mark.parametrize("event", _events())
def test_registered_trade_event_is_restored_with_its_typed_values(event) -> None:
    """4種の取引イベントは保存名から明示codecを選び、同じ値へ復元する。"""
    serializer = TradeEventJsonSerializer()
    message = StoredOutboxMessage(
        event_id=str(event.event_id),
        event_type=event_type_name(type(event)),
        payload=serializer.serialize(event),
        payload_schema_version=serializer.schema_version,
    )

    assert _registry().deserialize(message) == event


@pytest.mark.parametrize(
    ("event_type", "schema_version", "payload"),
    (("unknown:Event", 1, b"{}"), (event_type_name(TradeCancelledEvent), 2, b"{}"), (event_type_name(TradeCancelledEvent), 1, b"not-json")),
)
def test_unknown_type_schema_or_invalid_payload_is_permanent_failure(
    event_type: str,
    schema_version: int,
    payload: bytes,
) -> None:
    """登録外型・未対応schema・不正payloadは通常再試行しない永続的失敗に分類する。"""
    message = StoredOutboxMessage(
        event_id="1",
        event_type=event_type,
        payload=payload,
        payload_schema_version=schema_version,
    )

    with pytest.raises(PermanentOutboxMessageException):
        _registry().deserialize(message)


def test_duplicate_event_type_registration_is_rejected() -> None:
    """同じ保存名のcodecを上書きせず、構築時に誤配線を拒否する。"""
    registry = OutboxEventCodecRegistry()
    serializer = TradeEventJsonSerializer()
    registry.register(TradeCancelledEvent, serializer)

    with pytest.raises(ValueError, match="登録済み"):
        registry.register(TradeCancelledEvent, serializer)


def test_payload_event_id_must_match_outbox_row_identity() -> None:
    """payload内のevent_idが行の識別子と違うときは別イベントとして配送しない。"""
    serializer = TradeEventJsonSerializer()
    event = _events()[2]
    message = StoredOutboxMessage(
        event_id="different",
        event_type=event_type_name(type(event)),
        payload=serializer.serialize(event),  # type: ignore[arg-type]
        payload_schema_version=serializer.schema_version,
    )

    with pytest.raises(PermanentOutboxMessageException, match="event_id"):
        _registry().deserialize(message)
