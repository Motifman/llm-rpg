"""期限切れの提案を片付ける手順が、途中で落ちても回復すること。

片付けは 2 つの store をまたぐ (提案 store と inventory の予約)。**どちらの
中間状態が残るかは順序で決まる**。

- 削除 → 解除: 間で落ちると「提案は消えたのに凍結だけ残る」= その品を解放
  できる提案がもう無く、永久に使えない品が生まれる
- 解除 → 削除: 間で落ちると「凍結の無い期限切れ提案」が残るだけで、次の tick
  が拾い直して自己修復する

後者を選んでいる。ここではその回復を実際に確かめる。
"""

from __future__ import annotations

from typing import Any, List

from ai_rpg_world.application.trade.services.in_memory_pending_trade_offer_store import (
    InMemoryPendingTradeOfferStore,
)
from ai_rpg_world.application.trade.services.trade_offer_expiry_stage import (
    TradeOfferExpiryStage,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide

_A = PlayerId(1)
_B = PlayerId(2)


class _RecordingFreeze:
    """解除の呼び出しを数えるだけの凍結サービス代役。"""

    def __init__(self) -> None:
        self.released: List[int] = []

    def release_offer(self, offer: PendingTradeOffer) -> None:
        self.released.append(offer.offer_id.value)


def _store_with_offer(created_tick: int = 5) -> tuple:
    store = InMemoryPendingTradeOfferStore()
    offer = PendingTradeOffer.create(
        offer_id=store.next_offer_id(),
        offerer_player_id=_A,
        target_player_id=_B,
        gives=TradeSide(items=((10, 1),)),
        asks=TradeSide(gold=6),
        created_tick=created_tick,
        expires_in_ticks=10,
    )
    store.put(offer)
    return store, offer


class TestExpiryCleansUpInTheRightOrder:
    """期限を過ぎた提案は、凍結を解いてから片付けられる。"""

    def test_a_live_offer_is_left_alone(self) -> None:
        """期限内の提案には手を付けない。"""
        store, offer = _store_with_offer()
        freeze = _RecordingFreeze()

        TradeOfferExpiryStage(
            pending_trade_offer_store=store, trade_freeze_service=freeze,
        ).run(15)

        assert store.find(offer.offer_id) is not None
        assert freeze.released == []

    def test_an_expired_offer_is_released_and_removed(self) -> None:
        """期限を過ぎた提案は、凍結が解かれ store からも消える。"""
        store, offer = _store_with_offer()
        freeze = _RecordingFreeze()

        TradeOfferExpiryStage(
            pending_trade_offer_store=store, trade_freeze_service=freeze,
        ).run(16)

        assert freeze.released == [offer.offer_id.value]
        assert store.find(offer.offer_id) is None

    def test_both_parties_are_told(self) -> None:
        """流れたことを当事者へ知らせる (黙って消さない)。"""
        store, offer = _store_with_offer()
        told: List[Any] = []

        TradeOfferExpiryStage(
            pending_trade_offer_store=store,
            trade_freeze_service=_RecordingFreeze(),
            expiry_observer=told.append,
        ).run(16)

        assert [o.offer_id for o in told] == [offer.offer_id]

    def test_a_failing_observer_does_not_undo_the_cleanup(self) -> None:
        """知らせに失敗しても、片付け自体は完了している。

        ここで例外を上げると tick 全体が止まる。「観測だけ届かなかった」より
        「世界が進まない」方が悪い。
        """
        store, offer = _store_with_offer()

        def _boom(_offer: Any) -> None:
            raise RuntimeError("observation pipeline down")

        TradeOfferExpiryStage(
            pending_trade_offer_store=store,
            trade_freeze_service=_RecordingFreeze(),
            expiry_observer=_boom,
        ).run(16)

        assert store.find(offer.offer_id) is None


class TestTheCleanupRecoversFromAHalfDoneState:
    """解除だけ済んだ状態からでも、次の tick が片付け切る。"""

    def test_releasing_twice_is_harmless(self) -> None:
        """凍結の解除は二度呼んでも壊れない (冪等)。

        片付けが途中で落ちた提案を次の tick で拾い直すとき、既に解除済みの
        提案へもう一度呼ぶことになる。
        """
        store, offer = _store_with_offer()
        freeze = _RecordingFreeze()
        stage = TradeOfferExpiryStage(
            pending_trade_offer_store=store, trade_freeze_service=freeze,
        )

        stage.run(16)
        store.put(offer)  # 削除前に落ちた状況を作り直す
        stage.run(17)

        assert freeze.released == [offer.offer_id.value] * 2
        assert store.find(offer.offer_id) is None

    def test_an_offer_left_after_release_is_cleaned_next_tick(self) -> None:
        """解除済み・削除前で止まった提案を、次の tick が片付ける。

        これが「解除 → 削除」の順を選んだ理由そのもの。逆順だと、残るのは
        凍結だけになり、解放できる提案がもう存在しない。
        """
        store, offer = _store_with_offer()
        freeze = _RecordingFreeze()
        # 解除だけ済んで削除されなかった状態 (提案は store に残っている)
        freeze.release_offer(offer)
        assert store.find(offer.offer_id) is not None

        TradeOfferExpiryStage(
            pending_trade_offer_store=store, trade_freeze_service=freeze,
        ).run(16)

        assert store.find(offer.offer_id) is None
