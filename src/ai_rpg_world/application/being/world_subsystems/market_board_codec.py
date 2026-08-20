"""市場の掲示板の subsystem codec (経済統合 Phase 3)。

**store を足す PR で同時に入れる。** 板が保存・復元されないと、中断・再開で
板が消え、**預けた品と gold がまるごと消滅する**。出品者の所持品からは既に
引かれているので、戻す先を失う。Phase 2 の「提案だけ消えて凍結が残る」と
同じ型の事故で、症状が出るのは再開してしばらく経ってからになる。

板は**世界の状態**で、誰かの記憶ではない。だから `BeingMemorySnapshotService`
ではなく world snapshot 側に載せる。Being は世界をまたいで永続するが、
「板に何が並んでいるか」は世界の中の状態なので持ち越す意味が無い。

ID の払い出しも戻す。戻さないと、再開後に出した注文が復元済みの注文と同じ ID
になり、板が「同じ ID を二度置けません」で落ちる。再開した世界で誰も出品
できなくなる。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)
from ai_rpg_world.domain.trade.aggregate.market_board import MarketTrade
from ai_rpg_world.domain.trade.aggregate.market_order import MarketOrder
from ai_rpg_world.domain.trade.value_object.market_order_id import MarketOrderId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.trade.value_object.market_participant import (
    MarketParticipant,
    MarketParticipantKind,
)

SUBSYSTEM_KEY = "market_board"
SCHEMA_VERSION = 1


def _owner_to_dict(owner: MarketParticipant) -> dict[str, Any]:
    return {"kind": owner.kind.value, "entity_id": int(owner.entity_id)}


def _dict_to_owner(data: Any) -> MarketParticipant:
    if not isinstance(data, dict):
        raise ValueError(f"{SUBSYSTEM_KEY} owner must be a dict, got {type(data)}")
    try:
        kind = MarketParticipantKind(data["kind"])
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"{SUBSYSTEM_KEY} owner.kind unsupported: {data.get('kind')!r}"
        ) from exc
    return MarketParticipant(kind=kind, entity_id=int(data["entity_id"]))


def _decode_last_trades(raw_trades: Any) -> tuple[MarketTrade, ...]:
    """直近の約定を読み戻す。

    **鍵ごと欠けているのは許す。** 約定の記録が無い snapshot は「一度も約定
    していない」と同じ意味で、失うものが無い。読めた方がよいので版は上げない。
    形が壊れているときだけ落とす — 壊れた板で再開しない。
    """
    if not isinstance(raw_trades, list):
        raise ValueError(
            f"{SUBSYSTEM_KEY} last_trades must be a list, got {type(raw_trades)}"
        )
    trades = []
    for raw in raw_trades:
        if not isinstance(raw, dict):
            raise ValueError(f"{SUBSYSTEM_KEY} last_trade must be a dict, got {raw!r}")
        try:
            taker_side = MarketOrderSide(raw["taker_side"])
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"{SUBSYSTEM_KEY} last_trade.taker_side unsupported: "
                f"{raw.get('taker_side')!r}"
            ) from exc
        trades.append(
            MarketTrade(
                resting_order_id=MarketOrderId(int(raw["resting_order_id"])),
                item_spec_id=int(raw["item_spec_id"]),
                quantity=int(raw["quantity"]),
                unit_price_gold=int(raw["unit_price_gold"]),
                seller=_dict_to_owner(raw["seller"]),
                buyer=_dict_to_owner(raw["buyer"]),
                taker_side=taker_side,
                at_tick=int(raw["at_tick"]),
            )
        )
    return tuple(trades)


class MarketBoardSubsystemCodec(WorldSubsystemCodec):
    """``runtime._market_board_store`` を保存・復元する。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        store = getattr(runtime, "_market_board_store", None)
        if store is None:
            return {"schema_version": SCHEMA_VERSION, "orders": [], "last_trades": []}
        return {
            "schema_version": SCHEMA_VERSION,
            "last_trades": [
                {
                    "resting_order_id": int(trade.resting_order_id.value),
                    "item_spec_id": int(trade.item_spec_id),
                    "quantity": int(trade.quantity),
                    "unit_price_gold": int(trade.unit_price_gold),
                    "seller": _owner_to_dict(trade.seller),
                    "buyer": _owner_to_dict(trade.buyer),
                    "taker_side": trade.taker_side.value,
                    "at_tick": int(trade.at_tick),
                }
                for trade in store.board().last_trades
            ],
            "orders": [
                {
                    "order_id": int(order.order_id.value),
                    "side": order.side.value,
                    "owner": _owner_to_dict(order.owner),
                    "item_spec_id": int(order.item_spec_id),
                    "quantity": int(order.quantity),
                    "unit_price_gold": int(order.unit_price_gold),
                    "listed_at_tick": int(order.listed_at_tick),
                    "expires_at_tick": int(order.expires_at_tick),
                    "is_awaiting_collection": bool(order.is_awaiting_collection),
                }
                for order in store.board().orders
            ],
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        store = getattr(runtime, "_market_board_store", None)
        if store is None:
            return
        raw_orders = data.get("orders", [])
        if not isinstance(raw_orders, list):
            raise ValueError(
                f"{SUBSYSTEM_KEY} orders must be a list, got {type(raw_orders)}"
            )
        orders = []
        for raw in raw_orders:
            if not isinstance(raw, dict):
                raise ValueError(f"{SUBSYSTEM_KEY} order must be a dict, got {raw!r}")
            try:
                side = MarketOrderSide(raw["side"])
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f"{SUBSYSTEM_KEY} order.side unsupported: {raw.get('side')!r}"
                ) from exc
            orders.append(
                MarketOrder(
                    order_id=MarketOrderId(int(raw["order_id"])),
                    side=side,
                    owner=_dict_to_owner(raw["owner"]),
                    item_spec_id=int(raw["item_spec_id"]),
                    quantity=int(raw["quantity"]),
                    unit_price_gold=int(raw["unit_price_gold"]),
                    listed_at_tick=int(raw["listed_at_tick"]),
                    # **期限は保存値をそのまま戻す。** 復元時に
                    # listed + 既定期間で計算し直すと、シナリオの期間設定を
                    # 変えた後の再開で注文の寿命が伸び縮みする。
                    expires_at_tick=int(raw["expires_at_tick"]),
                    is_awaiting_collection=bool(
                        raw.get("is_awaiting_collection", False)
                    ),
                )
            )
        store.replace_all(orders, _decode_last_trades(data.get("last_trades", [])))


__all__ = [
    "MarketBoardSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
