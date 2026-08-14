"""同席したエージェント同士の取引提案 (PendingTradeOffer) の不変条件。

Phase 2 の取引は「A が B へ条件つきで持ちかけ、B が受けるか断る」形で、
give_item の無償版を条件つきへ広げたもの。提案は**二人の間にある状態**で、
どちらかの記憶ではないため world 側に持つ。

ここで縛るのは、成立しえない提案を作らせないこと。壊れた提案が store に
入ると、失敗が発火の瞬間ではなく承諾の瞬間に出て、原因が読めなくなる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import (
    PendingTradeOffer,
    TradeOfferState,
)
from ai_rpg_world.domain.trade.exception.trade_exception import (
    TradeOfferStateException,
    TradeOfferValidationException,
)
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide
from ai_rpg_world.domain.trade.value_object.trade_offer_id import TradeOfferId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_OFFERER = PlayerId(1)
_TARGET = PlayerId(2)


def _side(*, items: tuple = (), gold: int = 0) -> TradeSide:
    return TradeSide(items=items, gold=gold)


def _offer(
    *,
    gives: TradeSide | None = None,
    asks: TradeSide | None = None,
    offerer: PlayerId = _OFFERER,
    target: PlayerId = _TARGET,
    created_tick: int = 5,
    expires_in_ticks: int = 10,
) -> PendingTradeOffer:
    return PendingTradeOffer.create(
        offer_id=TradeOfferId(1),
        offerer_player_id=offerer,
        target_player_id=target,
        gives=gives if gives is not None else _side(items=((10, 1),)),
        asks=asks if asks is not None else _side(gold=6),
        created_tick=created_tick,
        expires_in_ticks=expires_in_ticks,
    )


class TestAnOfferIsBornPending:
    """作られた提案は、返事待ちの状態で期限を持つ。"""

    def test_a_new_offer_is_pending(self) -> None:
        """作った直後の提案は返事待ち状態になる。"""
        assert _offer().state is TradeOfferState.PENDING

    def test_the_deadline_is_the_creation_tick_plus_the_window(self) -> None:
        """期限は作られた tick に有効期間を足した tick になる。"""
        offer = _offer(created_tick=5, expires_in_ticks=10)

        assert offer.expires_at_tick == 15

    def test_it_is_expired_only_after_the_deadline_passes(self) -> None:
        """期限の tick までは生きており、それを過ぎたら期限切れと判定される。"""
        offer = _offer(created_tick=5, expires_in_ticks=10)

        assert not offer.is_expired_at(15)
        assert offer.is_expired_at(16)


class TestAnOfferMustBeSettleable:
    """成立しえない提案は、作る時点で弾く。"""

    def test_gold_on_both_sides_is_rejected(self) -> None:
        """両側に gold を置いた提案は作れない (金だけの両替に意味が無い)。"""
        with pytest.raises(TradeOfferValidationException):
            _offer(gives=_side(gold=10), asks=_side(gold=10))

    def test_an_empty_side_is_rejected(self) -> None:
        """片側が空の提案は作れない (一方的な譲渡は give_item の仕事)。"""
        with pytest.raises(TradeOfferValidationException):
            _offer(gives=_side(), asks=_side(gold=6))

    def test_offering_to_oneself_is_rejected(self) -> None:
        """自分自身への提案は作れない。"""
        with pytest.raises(TradeOfferValidationException):
            _offer(offerer=_OFFERER, target=_OFFERER)

    def test_a_non_positive_window_is_rejected(self) -> None:
        """有効期間が 0 以下の提案は作れない (作った瞬間に切れる提案を作らない)。"""
        with pytest.raises(TradeOfferValidationException):
            _offer(expires_in_ticks=0)

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_a_non_positive_quantity_is_rejected(self, quantity: int) -> None:
        """個数が 0 以下の品を含む提案は作れない。"""
        with pytest.raises(TradeOfferValidationException):
            _offer(gives=_side(items=((10, quantity),)))

    def test_negative_gold_is_rejected(self) -> None:
        """負の gold を含む提案は作れない。"""
        with pytest.raises(TradeOfferValidationException):
            _offer(asks=_side(gold=-1))

    def test_the_same_item_twice_on_one_side_is_rejected(self) -> None:
        """片側に同じ品を 2 度書いた提案は作れない (どちらの個数が効くか決まらない)。"""
        with pytest.raises(TradeOfferValidationException):
            _offer(gives=_side(items=((10, 1), (10, 2))))


class TestTheAnswerIsFinal:
    """返事は 1 度だけ。二度目は状態遷移として弾く。"""

    def test_accepting_marks_it_accepted(self) -> None:
        """承諾すると成立状態になる。"""
        offer = _offer()

        accepted = offer.accept()

        assert accepted.state is TradeOfferState.ACCEPTED
        # 元の提案は変わらない (不変オブジェクトとして扱う)
        assert offer.state is TradeOfferState.PENDING

    def test_declining_marks_it_declined(self) -> None:
        """断ると辞退状態になる。"""
        assert _offer().decline().state is TradeOfferState.DECLINED

    def test_expiring_marks_it_expired(self) -> None:
        """期限切れにすると流れた状態になる。"""
        assert _offer().expire().state is TradeOfferState.EXPIRED

    @pytest.mark.parametrize("answer", ["accept", "decline", "expire"])
    def test_answering_twice_is_rejected(self, answer: str) -> None:
        """一度返事のついた提案へ、もう一度返事はできない。

        形の誤り (ValidationException) ではなく状態の誤りなので、
        StateException 系で返す。呼び出し側が「作り方が悪い」と
        「もう終わっている」を取り違えないようにするため。
        """
        answered = _offer().accept()

        with pytest.raises(TradeOfferStateException):
            getattr(answered, answer)()
