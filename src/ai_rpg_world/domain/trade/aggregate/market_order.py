"""市場の板に出す注文 1 件 (経済統合 Phase 3)。

## 旧 TradeAggregate を使わない理由

旧集約は「アイテムの実体 1 つ ⇄ gold」の掲示モデルで、数量も単価も持たない。
「パン 2 個を 1 個 15G で」が書けず、板に並べたときに値が個数で割り切れない。
Phase 2 の `TradeSide` 寄り (品目 + 数量) に、板に要る単価を足した形で新しく
作る。旧集約の削除は実 run で検証してから。

## 単価で書く

「パン 3 個で 10G」のような割り切れない束は作れない。単価が小数になると
価格の時系列が汚れ、エージェントが値を比べるときの見え方も悪くなる。
「パン 2 個で 30G」は単価 15G × 2 で書けるので、表現力は落ちない。

## 不変オブジェクトとして扱う

部分約定は**残数を減らした新しい注文**を返す。同じ注文が二度削られる事故を、
状態の書き換えではなく生成の失敗として捕まえるため (Phase 2 の
`PendingTradeOffer` と同じ判断)。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ai_rpg_world.domain.trade.exception.trade_exception import (
    MarketOrderStateException,
    MarketOrderValidationException,
)
from ai_rpg_world.domain.trade.value_object.market_order_id import MarketOrderId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.trade.value_object.market_participant import MarketParticipant


def _require_positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MarketOrderValidationException(
            f"{field} は整数で指定してください (got {value!r})"
        )
    if value <= 0:
        raise MarketOrderValidationException(
            f"{field} は 1 以上で指定してください (got {value})"
        )
    return value


@dataclass(frozen=True)
class MarketOrder:
    """板に並ぶ注文 1 件。"""

    order_id: MarketOrderId
    side: MarketOrderSide
    owner: MarketParticipant
    item_spec_id: int
    quantity: int
    unit_price_gold: int
    listed_at_tick: int
    expires_at_tick: int
    #: 期限切れの返却が所持品の空き不足で果たせず、引き取りを待っている状態。
    is_awaiting_collection: bool = False

    @classmethod
    def create(
        cls,
        *,
        order_id: MarketOrderId,
        side: MarketOrderSide,
        owner: MarketParticipant,
        item_spec_id: int,
        quantity: int,
        unit_price_gold: int,
        listed_at_tick: int,
        expires_in_ticks: int,
    ) -> "MarketOrder":
        """板に載せられる注文だけを作る。"""
        if not isinstance(side, MarketOrderSide):
            raise MarketOrderValidationException(
                f"side は MarketOrderSide で指定してください (got {side!r})"
            )
        if not isinstance(owner, MarketParticipant):
            raise MarketOrderValidationException(
                f"owner は MarketParticipant で指定してください (got {owner!r})"
            )
        _require_positive_int(quantity, field="quantity")
        _require_positive_int(unit_price_gold, field="unit_price_gold")
        _require_positive_int(expires_in_ticks, field="expires_in_ticks")
        if isinstance(item_spec_id, bool) or not isinstance(item_spec_id, int):
            raise MarketOrderValidationException(
                f"item_spec_id は整数で指定してください (got {item_spec_id!r})"
            )
        if isinstance(listed_at_tick, bool) or not isinstance(listed_at_tick, int):
            raise MarketOrderValidationException(
                f"listed_at_tick は整数で指定してください (got {listed_at_tick!r})"
            )
        return cls(
            order_id=order_id,
            side=side,
            owner=owner,
            item_spec_id=item_spec_id,
            quantity=quantity,
            unit_price_gold=unit_price_gold,
            listed_at_tick=listed_at_tick,
            expires_at_tick=listed_at_tick + expires_in_ticks,
        )

    @property
    def total_gold(self) -> int:
        """注文全体の金額。単価から掛け算で出す (合計を別に持たない)。"""
        return self.unit_price_gold * self.quantity

    @property
    def is_exhausted(self) -> bool:
        """残数が尽きたか (板から外す判断は板の側)。"""
        return self.quantity <= 0

    def is_expired_at(self, current_tick: int) -> bool:
        """その手番の時点で期限を過ぎているか。

        期限の手番ちょうどはまだ生きている扱いにする。「40 手番置ける」と
        宣言した注文が 40 手番目に消えると、宣言と挙動が 1 手番ずれる。
        """
        return current_tick > self.expires_at_tick

    def filled_by(self, quantity: int) -> "MarketOrder":
        """その数量ぶんが約定した注文を返す。"""
        if self.is_awaiting_collection:
            raise MarketOrderStateException(
                f"引き取り待ちの注文は約定できません (order_id={self.order_id.value})"
            )
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise MarketOrderStateException(
                f"約定する数量は 1 以上の整数で指定してください (got {quantity!r})"
            )
        if quantity > self.quantity:
            # 超過を黙って切り詰めると、買った側は「3 つ買えた」と思っている
            # のに 2 つしか届かない。数え違いが観測と食い違う形で残る。
            raise MarketOrderStateException(
                f"残数を超えて約定できません "
                f"(order_id={self.order_id.value}, 残り {self.quantity}, 要求 {quantity})"
            )
        return replace(self, quantity=self.quantity - quantity)

    def repriced(self, new_unit_price: int) -> "MarketOrder":
        """単価だけを変えた注文を返す。

        期限は動かさない。伸びると値下げが**期限の延命**に使え、板に居座り
        続ける注文を作れてしまう。数量も動かさない (品は板に預けたまま)。
        """
        if self.is_awaiting_collection:
            raise MarketOrderStateException(
                f"引き取り待ちの注文は値を変えられません (order_id={self.order_id.value})"
            )
        _require_positive_int(new_unit_price, field="unit_price_gold")
        return replace(self, unit_price_gold=new_unit_price)

    def awaiting_collection(self) -> "MarketOrder":
        """引き取り待ちの状態にした注文を返す。"""
        return replace(self, is_awaiting_collection=True)


__all__ = ["MarketOrder"]
