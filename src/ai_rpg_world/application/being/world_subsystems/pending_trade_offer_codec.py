"""返事待ちの取引提案の subsystem codec (経済統合 Phase 2)。

**store を足す PR で同時に入れる。** 「あとで足す」と長走実験の終了 → 再開で
連続性が静かに壊れる (CLAUDE.md の per-Being store の教訓と同じ形)。

提案は**二人の間にある状態**で、どちらかの記憶ではない。だから
`BeingMemorySnapshotService` ではなく world snapshot 側に載せる。Being は
世界をまたいで永続するが、「誰に何を持ちかけたか」は世界の中の関係なので
持ち越す意味が無い。

ここで落とすと、再開のたびに提案が消える。**提示した品の凍結は
player_inventory 側に残る**ので、提案だけが消えると「誰の提案でもないのに
凍結されたままの品」が生まれ、二度と使えなくなる。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import (
    PendingTradeOffer,
    TradeOfferState,
)
from ai_rpg_world.domain.trade.value_object.trade_offer_id import TradeOfferId
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide

SUBSYSTEM_KEY = "pending_trade_offer"
SCHEMA_VERSION = 1


def _side_to_dict(side: TradeSide) -> dict[str, Any]:
    return {
        # (spec_id, quantity) の平坦な列にする。入れ子の dict を JSON へ
        # 落とすと spec_id が文字列 key に化けて、復元で int に戻し忘れる。
        "items": [[int(spec_id), int(quantity)] for spec_id, quantity in side.items],
        "gold": int(side.gold),
    }


def _dict_to_side(data: Any) -> TradeSide:
    if not isinstance(data, dict):
        raise ValueError(f"{SUBSYSTEM_KEY} side must be a dict, got {type(data)}")
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        raise ValueError(f"{SUBSYSTEM_KEY} side.items must be a list")
    items = []
    for entry in raw_items:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError(
                f"{SUBSYSTEM_KEY} side.items entry must be "
                f"[item_spec_id, quantity], got {entry!r}"
            )
        items.append((int(entry[0]), int(entry[1])))
    return TradeSide(items=tuple(items), gold=int(data.get("gold", 0)))


class PendingTradeOfferSubsystemCodec(WorldSubsystemCodec):
    """``runtime._pending_trade_offer_store`` を保存・復元する。"""

    @property
    def subsystem_key(self) -> str:
        return SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        store = getattr(runtime, "_pending_trade_offer_store", None)
        if store is None:
            return {"schema_version": SCHEMA_VERSION, "offers": []}
        return {
            "schema_version": SCHEMA_VERSION,
            "offers": [
                {
                    "offer_id": int(offer.offer_id.value),
                    "offerer_player_id": int(offer.offerer_player_id.value),
                    "target_player_id": int(offer.target_player_id.value),
                    "gives": _side_to_dict(offer.gives),
                    "asks": _side_to_dict(offer.asks),
                    "created_tick": int(offer.created_tick),
                    "expires_at_tick": int(offer.expires_at_tick),
                }
                for offer in store.list_all()
            ],
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"{SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected {SCHEMA_VERSION})"
            )
        store = getattr(runtime, "_pending_trade_offer_store", None)
        if store is None:
            return
        raw_offers = data.get("offers", [])
        if not isinstance(raw_offers, list):
            raise ValueError(
                f"{SUBSYSTEM_KEY} offers must be a list, got {type(raw_offers)}"
            )
        offers = []
        for raw in raw_offers:
            if not isinstance(raw, dict):
                raise ValueError(
                    f"{SUBSYSTEM_KEY} offer must be a dict, got {raw!r}"
                )
            created_tick = int(raw["created_tick"])
            expires_at_tick = int(raw["expires_at_tick"])
            offers.append(
                PendingTradeOffer(
                    offer_id=TradeOfferId(int(raw["offer_id"])),
                    offerer_player_id=PlayerId(int(raw["offerer_player_id"])),
                    target_player_id=PlayerId(int(raw["target_player_id"])),
                    gives=_dict_to_side(raw["gives"]),
                    asks=_dict_to_side(raw["asks"]),
                    created_tick=created_tick,
                    # **期限は保存値をそのまま戻す。** 復元時に
                    # created + 既定期間で計算し直すと、シナリオの期間設定を
                    # 変えた後の再開で提案の寿命が伸び縮みする。
                    expires_at_tick=expires_at_tick,
                    state=TradeOfferState.PENDING,
                )
            )
        store.replace_all(offers)


__all__ = [
    "PendingTradeOfferSubsystemCodec",
    "SUBSYSTEM_KEY",
    "SCHEMA_VERSION",
]
