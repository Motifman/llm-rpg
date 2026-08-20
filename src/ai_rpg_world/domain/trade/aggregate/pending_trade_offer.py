"""同席したエージェント同士の取引提案 (Phase 2)。

## 旧 TradeAggregate を使わない理由

旧集約は「1 アイテム ⇄ gold を掲示板に出す」モデルで、掲示・検索・購入の
非同期な流れを前提にしている。こちらは**同席している相手へ持ちかけ、相手の
手番で受けるか断る**同期 1 往復で、状態遷移も語彙も違う。無理に共有すると
どちらの意味も濁る。掲示板型 (B2) は旧集約の土台をそのまま使う。

## 提案は誰の状態か

**二人の間にある状態**で、どちらかの記憶ではない。したがって per-Being の
記憶ではなく world 側に持ち、world snapshot で保存する。

## 不変オブジェクトとして扱う

返事 (accept / decline / expire) は新しい提案を返す。同じ提案に二度返事が
つく事故を、状態の書き換えではなく生成の失敗として捕まえるため。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.exception.trade_exception import (
    TradeOfferStateException,
    TradeOfferValidationException,
)
from ai_rpg_world.domain.trade.value_object.trade_offer_id import TradeOfferId
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide


class TradeOfferState(str, Enum):
    """提案の状態。返事がつくと終わりで、そこから戻らない。"""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


@dataclass(frozen=True)
class PendingTradeOffer:
    """返事待ちの取引提案 1 件。"""

    offer_id: TradeOfferId
    offerer_player_id: PlayerId
    target_player_id: PlayerId
    gives: TradeSide
    asks: TradeSide
    created_tick: int
    expires_at_tick: int
    state: TradeOfferState = TradeOfferState.PENDING

    @classmethod
    def create(
        cls,
        *,
        offer_id: TradeOfferId,
        offerer_player_id: PlayerId,
        target_player_id: PlayerId,
        gives: TradeSide,
        asks: TradeSide,
        created_tick: int,
        expires_in_ticks: int,
    ) -> "PendingTradeOffer":
        """成立しうる提案だけを作る。"""
        if not isinstance(gives, TradeSide) or not isinstance(asks, TradeSide):
            raise TradeOfferValidationException("gives / asks は TradeSide で渡してください")
        if offerer_player_id == target_player_id:
            raise TradeOfferValidationException("自分自身へは持ちかけられません")
        if gives.is_empty or asks.is_empty:
            raise TradeOfferValidationException(
                "gives と asks の両方に中身が要ります "
                "(片側だけの譲渡は give_item の仕事)"
            )
        if gives.has_gold and asks.has_gold:
            # 金だけを両替する取引に意味が無く、決済も「差額を動かす」のか
            # 「両方向に動かす」のかで解釈が割れる。片側だけに寄せる。
            raise TradeOfferValidationException(
                "gold は片側にだけ置けます (両側に gold のある提案は作れません)"
            )
        if isinstance(expires_in_ticks, bool) or not isinstance(expires_in_ticks, int):
            raise TradeOfferValidationException("expires_in_ticks は整数で指定してください")
        if expires_in_ticks <= 0:
            raise TradeOfferValidationException(
                "expires_in_ticks は 1 以上で指定してください "
                "(作った瞬間に切れる提案を作らない)"
            )
        if isinstance(created_tick, bool) or not isinstance(created_tick, int):
            raise TradeOfferValidationException("created_tick は整数で指定してください")
        return cls(
            offer_id=offer_id,
            offerer_player_id=offerer_player_id,
            target_player_id=target_player_id,
            gives=gives,
            asks=asks,
            created_tick=created_tick,
            expires_at_tick=created_tick + expires_in_ticks,
        )

    @property
    def is_pending(self) -> bool:
        return self.state is TradeOfferState.PENDING

    def is_expired_at(self, current_tick: int) -> bool:
        """その tick の時点で期限を過ぎているか。

        期限の tick ちょうどはまだ生きている扱いにする。「10 tick 待つ」と
        宣言した提案が 10 tick 目に切れると、宣言と挙動が 1 tick ずれる。
        """
        return current_tick > self.expires_at_tick

    def accept(self) -> "PendingTradeOffer":
        """承諾された状態の提案を返す。"""
        return self._answered(TradeOfferState.ACCEPTED)

    def decline(self) -> "PendingTradeOffer":
        """辞退された状態の提案を返す。"""
        return self._answered(TradeOfferState.DECLINED)

    def expire(self) -> "PendingTradeOffer":
        """流れた状態の提案を返す。"""
        return self._answered(TradeOfferState.EXPIRED)

    def _answered(self, state: TradeOfferState) -> "PendingTradeOffer":
        if not self.is_pending:
            raise TradeOfferStateException(
                f"既に {self.state.value} の提案には返事できません "
                f"(offer_id={self.offer_id.value})"
            )
        return replace(self, state=state)
