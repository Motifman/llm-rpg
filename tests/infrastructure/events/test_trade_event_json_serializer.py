"""取引イベントを永続outbox用JSONへ安全に往復できることを保証する。"""

from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_listing_projection import (
    TradeListingProjection,
)
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import (
    TradeRequestedGold,
)
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.infrastructure.events.trade_event_json_serializer import (
    TradeEventJsonSerializer,
)


_NOW = datetime(2026, 8, 14, 1, 2, 3, tzinfo=timezone.utc)
_LISTING = TradeListingProjection(
    seller_display_name="Alice",
    item_name="Key",
    item_quantity=2,
    item_type=ItemType.CONSUMABLE,
    item_rarity=Rarity.RARE,
    item_description="A key",
    item_equipment_type=None,
    durability_current=None,
    durability_max=None,
)


def _events() -> tuple[object, ...]:
    common = {
        "event_id": 123456789012345678901234567890,
        "occurred_at": _NOW,
        "aggregate_id": TradeId(7),
        "aggregate_type": "TradeAggregate",
    }
    return (
        TradeOfferedEvent(
            **common,
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(10),
            requested_gold=TradeRequestedGold.of(50),
            trade_scope=TradeScope.direct_trade(PlayerId(2)),
            listing_projection=_LISTING,
            trade_created_at=_NOW,
        ),
        TradeAcceptedEvent(
            **common,
            buyer_id=PlayerId(2),
            buyer_display_name="Bob",
            listing_projection=_LISTING,
            seller_id=PlayerId(1),
            offered_item_id=ItemInstanceId(10),
            requested_gold=TradeRequestedGold.of(50),
            trade_created_at=_NOW,
        ),
        TradeCancelledEvent(**common),
        TradeDeclinedEvent(**common, decliner_id=PlayerId(2)),
    )


@pytest.mark.parametrize("event", _events())
def test_trade_event_round_trip_preserves_every_value(event: object) -> None:
    """4種の取引イベントはschema version付きJSONを介して同じ値へ復元される。"""
    serializer = TradeEventJsonSerializer()

    payload = serializer.serialize(event)  # type: ignore[arg-type]
    restored = serializer.deserialize(payload, type(event))  # type: ignore[arg-type]

    assert restored == event


def test_unknown_event_type_is_rejected() -> None:
    """対応外イベントを渡すと不完全なpayloadを保存せず明示的に拒否する。"""
    serializer = TradeEventJsonSerializer()

    with pytest.raises(TypeError, match="対応していない"):
        serializer.serialize(object())  # type: ignore[arg-type]


def test_invalid_persisted_scalar_is_not_silently_coerced() -> None:
    """boolのIDなど壊れたJSON値を整数へ暗黙変換せず読込み時に停止する。"""
    serializer = TradeEventJsonSerializer()
    event = _events()[2]
    raw = json.loads(serializer.serialize(event).decode("utf-8"))  # type: ignore[arg-type]
    raw["aggregate_id"] = True

    with pytest.raises(ValueError, match="aggregate_id"):
        serializer.deserialize(
            json.dumps(raw).encode("utf-8"),
            TradeCancelledEvent,
        )


def test_naive_persisted_datetime_is_rejected() -> None:
    """タイムゾーンのない日時を復元せず、配送順序の曖昧化を防ぐ。"""
    serializer = TradeEventJsonSerializer()
    event = _events()[2]
    raw = json.loads(serializer.serialize(event).decode("utf-8"))  # type: ignore[arg-type]
    raw["occurred_at"] = "2026-08-14T01:02:03"

    with pytest.raises(ValueError, match="タイムゾーン"):
        serializer.deserialize(
            json.dumps(raw).encode("utf-8"),
            TradeCancelledEvent,
        )


@pytest.mark.parametrize(
    ("event_index", "field_name"),
    ((2, "occurred_at"), (0, "trade_created_at"), (1, "trade_created_at")),
)
def test_naive_datetime_is_rejected_before_persistence(
    event_index: int,
    field_name: str,
) -> None:
    """タイムゾーンのない日時をoutboxへ保存せず、業務状態のcommit前に停止する。"""
    event = _events()[event_index]
    object.__setattr__(event, field_name, datetime(2026, 8, 14, 1, 2, 3))

    with pytest.raises(ValueError, match=field_name):
        TradeEventJsonSerializer().serialize(event)  # type: ignore[arg-type]
