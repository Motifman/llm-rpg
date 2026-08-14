"""返事待ちの取引提案を保持する store の挙動。

集約は 1 件の提案の中しか見ないので、「同じ相手へ既に持ちかけている」
「同じ品を別の提案にも出している」はここでしか判定できない。次の PR で
入れる凍結が、この集計をそのまま使う。
"""

from __future__ import annotations

from ai_rpg_world.application.trade.services.in_memory_pending_trade_offer_store import (
    InMemoryPendingTradeOfferStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide

_A = PlayerId(1)
_B = PlayerId(2)
_C = PlayerId(3)


def _offer(
    store: InMemoryPendingTradeOfferStore,
    *,
    offerer: PlayerId = _A,
    target: PlayerId = _B,
    gives: TradeSide | None = None,
    asks: TradeSide | None = None,
    created_tick: int = 5,
    expires_in_ticks: int = 10,
) -> PendingTradeOffer:
    offer = PendingTradeOffer.create(
        offer_id=store.next_offer_id(),
        offerer_player_id=offerer,
        target_player_id=target,
        gives=gives if gives is not None else TradeSide(items=((10, 1),)),
        asks=asks if asks is not None else TradeSide(gold=6),
        created_tick=created_tick,
        expires_in_ticks=expires_in_ticks,
    )
    store.put(offer)
    return offer


class TestTheStoreKeepsOnlyLiveOffers:
    """保持するのは返事待ちの提案だけ。"""

    def test_a_pending_offer_is_kept(self) -> None:
        """返事待ちの提案は保持され、ID で引ける。"""
        store = InMemoryPendingTradeOfferStore()

        offer = _offer(store)

        assert store.find(offer.offer_id) == offer

    def test_an_answered_offer_is_dropped(self) -> None:
        """返事のついた提案を put すると、保持から外れる。

        承諾・辞退・期限切れのどれでも「もう待っていない」ので、同じ扱いに
        する。残すと二重承諾の余地が生まれる。
        """
        store = InMemoryPendingTradeOfferStore()
        offer = _offer(store)

        store.put(offer.accept())

        assert store.find(offer.offer_id) is None
        assert store.list_all() == ()

    def test_ids_are_unique_across_offers(self) -> None:
        """払い出す提案 ID は重複しない。"""
        store = InMemoryPendingTradeOfferStore()

        first = _offer(store, target=_B)
        second = _offer(store, target=_C)

        assert first.offer_id != second.offer_id


class TestFindingOffersByPerson:
    """誰宛て / 誰発の提案かで引ける。"""

    def test_offers_are_listed_for_their_target(self) -> None:
        """自分宛ての提案だけが返る。"""
        store = InMemoryPendingTradeOfferStore()
        to_b = _offer(store, offerer=_A, target=_B)
        _offer(store, offerer=_A, target=_C)

        assert store.list_for_target(_B) == (to_b,)

    def test_offers_are_listed_for_their_offerer(self) -> None:
        """自分が出した提案だけが返る。"""
        store = InMemoryPendingTradeOfferStore()
        from_a = _offer(store, offerer=_A, target=_B)
        _offer(store, offerer=_C, target=_B)

        assert store.list_from_offerer(_A) == (from_a,)

    def test_a_second_offer_to_the_same_person_is_detectable(self) -> None:
        """同じ相手への提案が既に生きていることを判定できる。

        二重提案を弾くのはツール側の仕事だが、判定材料はここが持つ。
        """
        store = InMemoryPendingTradeOfferStore()
        _offer(store, offerer=_A, target=_B)

        assert store.has_offer_between(_A, _B)
        assert not store.has_offer_between(_A, _C)
        assert not store.has_offer_between(_B, _A), "向きを区別していない"


class TestWhatIsAlreadyCommitted:
    """提案に出している品と gold を集計できる (凍結の材料)。"""

    def test_items_across_offers_are_summed_per_spec(self) -> None:
        """複数の提案に出している同じ品は、合計数で数えられる。"""
        store = InMemoryPendingTradeOfferStore()
        _offer(store, target=_B, gives=TradeSide(items=((10, 1),)))
        _offer(store, target=_C, gives=TradeSide(items=((10, 2), (11, 1))))

        assert store.committed_item_quantities(_A) == {10: 3, 11: 1}

    def test_gold_across_offers_is_summed(self) -> None:
        """複数の提案に出している gold は合計される。

        gold は片側にしか置けないので、gold を出す提案の asks は品になる。
        """
        store = InMemoryPendingTradeOfferStore()
        _offer(store, target=_B, gives=TradeSide(gold=10), asks=TradeSide(items=((20, 1),)))
        _offer(store, target=_C, gives=TradeSide(gold=5), asks=TradeSide(items=((21, 1),)))

        assert store.committed_gold(_A) == 15

    def test_answered_offers_no_longer_commit_anything(self) -> None:
        """返事のついた提案は集計から外れる (凍結が解ける)。"""
        store = InMemoryPendingTradeOfferStore()
        offer = _offer(store, gives=TradeSide(items=((10, 1),)))

        store.put(offer.decline())

        assert store.committed_item_quantities(_A) == {}


class TestExpiryIsDetectedButNotApplied:
    """期限切れの検出は store、状態遷移と観測は呼び出し側。"""

    def test_offers_past_their_deadline_are_listed(self) -> None:
        """期限を過ぎた提案を列挙できる。"""
        store = InMemoryPendingTradeOfferStore()
        offer = _offer(store, created_tick=5, expires_in_ticks=10)

        assert store.expired_offers(15) == ()
        assert store.expired_offers(16) == (offer,)

    def test_listing_does_not_change_their_state(self) -> None:
        """列挙しただけでは状態が変わらない。

        store が状態を進めて観測まで出すと、保存・復元のたびに「流れた」が
        二重に届きうる。遷移と観測は tick stage の仕事にする。
        """
        store = InMemoryPendingTradeOfferStore()
        offer = _offer(store, created_tick=5, expires_in_ticks=10)

        store.expired_offers(16)

        assert store.find(offer.offer_id).is_pending


class TestRestoringFromASnapshot:
    """復元では保持内容を丸ごと置き換える。"""

    def test_replace_all_swaps_the_contents(self) -> None:
        """復元すると、それまでの提案は残らない。"""
        store = InMemoryPendingTradeOfferStore()
        _offer(store, target=_B)
        restored = PendingTradeOffer.create(
            offer_id=store.next_offer_id(),
            offerer_player_id=_C,
            target_player_id=_A,
            gives=TradeSide(items=((99, 1),)),
            asks=TradeSide(gold=1),
            created_tick=1,
            expires_in_ticks=10,
        )

        store.replace_all([restored])

        assert store.list_all() == (restored,)

    def test_new_ids_do_not_collide_with_restored_ones(self) -> None:
        """復元後に払い出す ID は、復元した提案の ID とぶつからない。"""
        store = InMemoryPendingTradeOfferStore()
        restored = PendingTradeOffer.create(
            offer_id=store.next_offer_id(),
            offerer_player_id=_C,
            target_player_id=_A,
            gives=TradeSide(items=((99, 1),)),
            asks=TradeSide(gold=1),
            created_tick=1,
            expires_in_ticks=10,
        )
        store.replace_all([restored])

        assert store.next_offer_id().value > restored.offer_id.value
