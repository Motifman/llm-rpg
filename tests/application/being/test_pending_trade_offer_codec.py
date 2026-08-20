"""返事待ちの取引提案が、保存と復元を跨いで残る (経済統合 Phase 2)。

ここで落ちると、再開のたびに提案だけが消える。**提示した品の凍結は
player_inventory 側に残る**ので、提案が消えると「誰の提案でもないのに凍結
されたままの品」が生まれ、その品は二度と使えなくなる。
"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.world_subsystems.pending_trade_offer_codec import (
    PendingTradeOfferSubsystemCodec,
)
from ai_rpg_world.application.trade.services.in_memory_pending_trade_offer_store import (
    InMemoryPendingTradeOfferStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide


class _Runtime:
    """codec が読む属性だけを持つ最小の runtime 代役。"""

    def __init__(self, store: InMemoryPendingTradeOfferStore) -> None:
        self._pending_trade_offer_store = store


def _offer(store: InMemoryPendingTradeOfferStore) -> PendingTradeOffer:
    offer = PendingTradeOffer.create(
        offer_id=store.next_offer_id(),
        offerer_player_id=PlayerId(1),
        target_player_id=PlayerId(2),
        gives=TradeSide(items=((10, 2), (11, 1))),
        asks=TradeSide(gold=6),
        created_tick=5,
        expires_in_ticks=10,
    )
    store.put(offer)
    return offer


class TestOffersSurviveTheSnapshot:
    """保存して復元すると、提案がそのまま戻る。"""

    def test_an_offer_round_trips(self) -> None:
        """提案の相手・中身・期限が、保存と復元を跨いで変わらない。"""
        codec = PendingTradeOfferSubsystemCodec()
        source = InMemoryPendingTradeOfferStore()
        original = _offer(source)

        restored_store = InMemoryPendingTradeOfferStore()
        codec.restore(_Runtime(restored_store), codec.capture(_Runtime(source)))

        assert restored_store.list_all() == (original,)

    def test_the_deadline_is_restored_as_saved(self) -> None:
        """期限は保存された値がそのまま戻る (復元時に計算し直さない)。

        再計算すると、シナリオの期間設定を変えた後の再開で提案の寿命が
        伸び縮みする。保存時点の約束をそのまま守る。
        """
        codec = PendingTradeOfferSubsystemCodec()
        source = InMemoryPendingTradeOfferStore()
        original = _offer(source)
        payload = codec.capture(_Runtime(source))
        payload["offers"][0]["created_tick"] = 999  # 期限と矛盾する値を入れる

        restored_store = InMemoryPendingTradeOfferStore()
        codec.restore(_Runtime(restored_store), payload)

        assert restored_store.list_all()[0].expires_at_tick == original.expires_at_tick

    def test_an_empty_store_round_trips(self) -> None:
        """提案が 1 件も無い世界でも、保存と復元が通る。"""
        codec = PendingTradeOfferSubsystemCodec()
        store = InMemoryPendingTradeOfferStore()

        codec.restore(_Runtime(store), codec.capture(_Runtime(store)))

        assert store.list_all() == ()

    def test_restoring_replaces_what_was_there(self) -> None:
        """復元は置き換えで、復元前の提案は残らない。"""
        codec = PendingTradeOfferSubsystemCodec()
        source = InMemoryPendingTradeOfferStore()
        payload = codec.capture(_Runtime(source))  # 空の状態を保存
        target = InMemoryPendingTradeOfferStore()
        _offer(target)

        codec.restore(_Runtime(target), payload)

        assert target.list_all() == ()


class TestTheCodecRefusesBrokenPayloads:
    """壊れた payload は黙って無視せず落とす。"""

    def test_an_unknown_schema_version_is_rejected(self) -> None:
        """知らない schema_version は落とす (黙って読み飛ばさない)。"""
        codec = PendingTradeOfferSubsystemCodec()
        store = InMemoryPendingTradeOfferStore()

        try:
            codec.restore(_Runtime(store), {"schema_version": 99, "offers": []})
        except ValueError as exc:
            assert "schema_version" in str(exc)
        else:  # pragma: no cover - 失敗時のみ到達
            raise AssertionError("未知の schema_version が素通りした")

    def test_a_runtime_without_the_store_is_tolerated(self) -> None:
        """store を持たない構成 (最小 wiring) では何もしない。"""
        codec = PendingTradeOfferSubsystemCodec()

        class _Bare:
            pass

        assert codec.capture(_Bare()) == {"schema_version": 1, "offers": []}
        codec.restore(_Bare(), {"schema_version": 1, "offers": []})
