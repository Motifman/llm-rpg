"""取引ドメインイベントの永続outbox向けJSON codec。"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Type

from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.enum.trade_enum import TradeType
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


_SCHEMA_VERSION = 1
_SUPPORTED_EVENT_TYPES = (
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
)


def _require_mapping(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label}はobjectである必要があります")
    return raw


def _require_string(raw: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(raw, str) or (not allow_empty and not raw):
        raise ValueError(f"{label}は文字列である必要があります")
    return raw


def _require_int(raw: Any, label: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"{label}は整数である必要があります")
    return raw


def _require_optional_int(raw: Any, label: str) -> int | None:
    return None if raw is None else _require_int(raw, label)


def _require_datetime(raw: Any, label: str) -> datetime:
    value = _require_string(raw, label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label}はISO 8601日時である必要があります") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label}はタイムゾーン付きである必要があります")
    return parsed


class TradeEventJsonSerializer:
    """4種の取引イベントを型付き値へ戻せるJSONとして保存する。"""

    @property
    def schema_version(self) -> int:
        return _SCHEMA_VERSION

    def serialize(self, event: DomainEvent) -> bytes:
        """対応する取引イベントをUTF-8 JSONへ変換する。"""
        if not isinstance(event, _SUPPORTED_EVENT_TYPES):
            raise TypeError(
                f"対応していない取引イベントです: {type(event).__name__}"
            )
        payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "event_type": type(event).__name__,
            "event_id": str(event.event_id),
            "occurred_at": event.occurred_at.isoformat(),
            "aggregate_id": int(event.aggregate_id),
            "aggregate_type": str(event.aggregate_type),
            "occurred_tick": (
                None if event.occurred_tick is None else event.occurred_tick.value
            ),
        }
        if isinstance(event, TradeOfferedEvent):
            payload.update(
                seller_id=int(event.seller_id),
                offered_item_id=int(event.offered_item_id),
                requested_gold=event.requested_gold.value,
                trade_scope=self._scope_to_dict(event.trade_scope),
                listing_projection=self._listing_to_dict(event.listing_projection),
                trade_created_at=event.trade_created_at.isoformat(),
            )
        elif isinstance(event, TradeAcceptedEvent):
            payload.update(
                buyer_id=int(event.buyer_id),
                buyer_display_name=event.buyer_display_name,
                listing_projection=self._listing_to_dict(event.listing_projection),
                seller_id=int(event.seller_id),
                offered_item_id=int(event.offered_item_id),
                requested_gold=event.requested_gold.value,
                trade_created_at=event.trade_created_at.isoformat(),
            )
        elif isinstance(event, TradeDeclinedEvent):
            payload["decliner_id"] = int(event.decliner_id)
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def deserialize(
        self,
        payload: bytes,
        event_type: Type[DomainEvent],
    ) -> DomainEvent:
        """JSONを指定された取引イベント型へ復元する。"""
        if event_type not in _SUPPORTED_EVENT_TYPES:
            raise TypeError(f"対応していない取引イベント型です: {event_type!r}")
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("取引イベントpayloadはUTF-8 JSONである必要があります") from error
        raw = _require_mapping(decoded, "取引イベントpayload")
        if _require_int(raw.get("schema_version"), "schema_version") != _SCHEMA_VERSION:
            raise ValueError(
                "未対応の取引イベントschema versionです: "
                f"{raw.get('schema_version')!r}"
            )
        if _require_string(raw.get("event_type"), "event_type") != event_type.__name__:
            raise ValueError("payloadのevent_typeと復元先の型が一致しません")
        event_id_raw = _require_string(raw.get("event_id"), "event_id")
        if not event_id_raw.isdecimal():
            raise ValueError("event_idは10進整数文字列である必要があります")
        occurred_tick = _require_optional_int(raw.get("occurred_tick"), "occurred_tick")
        common: dict[str, Any] = {
            "event_id": int(event_id_raw),
            "occurred_at": _require_datetime(raw.get("occurred_at"), "occurred_at"),
            "aggregate_id": TradeId(_require_int(raw.get("aggregate_id"), "aggregate_id")),
            "aggregate_type": _require_string(raw.get("aggregate_type"), "aggregate_type"),
            "occurred_tick": (
                None if occurred_tick is None else WorldTick(occurred_tick)
            ),
        }
        if event_type is TradeOfferedEvent:
            return TradeOfferedEvent(
                **common,
                seller_id=PlayerId(_require_int(raw.get("seller_id"), "seller_id")),
                offered_item_id=ItemInstanceId(
                    _require_int(raw.get("offered_item_id"), "offered_item_id")
                ),
                requested_gold=TradeRequestedGold.of(
                    _require_int(raw.get("requested_gold"), "requested_gold")
                ),
                trade_scope=self._dict_to_scope(raw.get("trade_scope")),
                listing_projection=self._dict_to_listing(
                    raw.get("listing_projection")
                ),
                trade_created_at=_require_datetime(
                    raw.get("trade_created_at"), "trade_created_at"
                ),
            )
        if event_type is TradeAcceptedEvent:
            return TradeAcceptedEvent(
                **common,
                buyer_id=PlayerId(_require_int(raw.get("buyer_id"), "buyer_id")),
                buyer_display_name=_require_string(
                    raw.get("buyer_display_name"), "buyer_display_name"
                ),
                listing_projection=self._dict_to_listing(
                    raw.get("listing_projection")
                ),
                seller_id=PlayerId(_require_int(raw.get("seller_id"), "seller_id")),
                offered_item_id=ItemInstanceId(
                    _require_int(raw.get("offered_item_id"), "offered_item_id")
                ),
                requested_gold=TradeRequestedGold.of(
                    _require_int(raw.get("requested_gold"), "requested_gold")
                ),
                trade_created_at=_require_datetime(
                    raw.get("trade_created_at"), "trade_created_at"
                ),
            )
        if event_type is TradeDeclinedEvent:
            return TradeDeclinedEvent(
                **common,
                decliner_id=PlayerId(
                    _require_int(raw.get("decliner_id"), "decliner_id")
                ),
            )
        return TradeCancelledEvent(**common)

    @staticmethod
    def _scope_to_dict(scope: TradeScope) -> dict[str, Any]:
        return {
            "trade_type": scope.trade_type.value,
            "target_player_id": (
                None
                if scope.target_player_id is None
                else int(scope.target_player_id)
            ),
        }

    @staticmethod
    def _dict_to_scope(raw: Any) -> TradeScope:
        raw = _require_mapping(raw, "trade_scope")
        trade_type = TradeType(_require_string(raw.get("trade_type"), "trade_type"))
        target = raw.get("target_player_id")
        if trade_type is TradeType.DIRECT:
            return TradeScope.direct_trade(
                PlayerId(_require_int(target, "target_player_id"))
            )
        if target is not None:
            raise ValueError("global tradeのtarget_player_idはnullである必要があります")
        return TradeScope.global_trade()

    @staticmethod
    def _listing_to_dict(listing: TradeListingProjection) -> dict[str, Any]:
        return {
            "seller_display_name": listing.seller_display_name,
            "item_name": listing.item_name,
            "item_quantity": listing.item_quantity,
            "item_type": listing.item_type.value,
            "item_rarity": listing.item_rarity.value,
            "item_description": listing.item_description,
            "item_equipment_type": (
                None
                if listing.item_equipment_type is None
                else listing.item_equipment_type.value
            ),
            "durability_current": listing.durability_current,
            "durability_max": listing.durability_max,
        }

    @staticmethod
    def _dict_to_listing(raw: Any) -> TradeListingProjection:
        raw = _require_mapping(raw, "listing_projection")
        equipment = raw.get("item_equipment_type")
        return TradeListingProjection(
            seller_display_name=_require_string(
                raw.get("seller_display_name"), "seller_display_name"
            ),
            item_name=_require_string(raw.get("item_name"), "item_name"),
            item_quantity=_require_int(raw.get("item_quantity"), "item_quantity"),
            item_type=ItemType(_require_string(raw.get("item_type"), "item_type")),
            item_rarity=Rarity(
                _require_string(raw.get("item_rarity"), "item_rarity")
            ),
            item_description=_require_string(
                raw.get("item_description"), "item_description", allow_empty=True
            ),
            item_equipment_type=(
                None
                if equipment is None
                else EquipmentType(
                    _require_string(equipment, "item_equipment_type")
                )
            ),
            durability_current=_require_optional_int(
                raw.get("durability_current"), "durability_current"
            ),
            durability_max=_require_optional_int(
                raw.get("durability_max"), "durability_max"
            ),
        )


__all__ = ["TradeEventJsonSerializer"]
