"""板の上で起きることが、周りの人に見える (経済統合 Phase 3)。

**届いた観測そのものを見る。** プロンプト全文の部分文字列検査は書かない —
同席者の名前も品名も別の節に出るので、観測が 1 件も届かなくても緑になる
(PR #1165 で実際に空振りしていた)。

板の上で起きることは 5 種類ある: 出品 / 値の付け直し / 約定 / 取り下げ /
期限切れ。どれか 1 つでも欠けると「板は動いているのに誰も気づかない」箇所が
残る。特に**値の付け直し**は、この実験でいちばん見たい「価格が変わる瞬間」
そのものなので、場に居る人に見えないと値動きが社会的な出来事にならない。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_MINA = PlayerId(3)
_BREAD = "焼きたてのパン"
_HERB = "薬草"


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    """板のある市場町。3 人が広場に居る。"""
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    spawn = raw["players"][0]["spawn_spot"]
    for pid, name in (("tom", "トム"), ("mina", "ミナ")):
        raw["players"].append({
            "id": pid, "name": name, "spawn_spot": spawn,
            "initial_items": [], "initial_gold": 200,
            "persona_prompt": f"あなたは{name}。",
        })
    raw["market"] = {"board_spot": "market_square"}
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _spec_id(runtime: Any, label: str) -> int:
    return runtime._item_spec_repo.find_by_name(label).item_spec_id.value


def _give(runtime: Any, player_id: PlayerId, label: str, count: int = 1) -> None:
    grant_item_specs_to_inventory(
        player_id,
        tuple(ItemSpecId.create(_spec_id(runtime, label)) for _ in range(count)),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _drain(runtime: Any, player_id: PlayerId) -> List[Any]:
    """その人に届いた観測の中身を取り出す。

    バッファは (発生時刻 + 観測) の entry を返すので、観測そのものを見る。
    """
    return [entry.output for entry in runtime._obs_buffer.drain(player_id)]


def _drain_all(runtime: Any) -> None:
    for pid in (1, 2, 3):
        _drain(runtime, PlayerId(pid))


def _market_observations(runtime: Any, player_id: PlayerId) -> List[Any]:
    return [
        o
        for o in _drain(runtime, player_id)
        if (o.structured or {}).get("type") == "market_board_activity"
    ]


def _list_bread(runtime: Any, seller: PlayerId, *, quantity: int, price: int) -> Any:
    _give(runtime, seller, _BREAD, quantity)
    return runtime._market_service.place_sell_order(
        seller, item_label=_BREAD, quantity=quantity, unit_price=price,
        current_tick=runtime.current_tick(),
    )


def _walk_away(runtime: Any, player_id: PlayerId) -> None:
    from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

    graph = runtime._spot_graph_repo.find_graph()
    here = graph.get_entity_spot(EntityId.create(int(player_id)))
    elsewhere = next(
        spot for spot in graph.neighbor_spot_ids_for_routing(here) if spot != here
    )
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(EntityId.create(int(player_id)), elsewhere)
    runtime._spot_graph_repo.save(graph)


class TestListingIsSeenByThoseAtTheBoard:
    """出品は、板の前に居る人に見える。"""

    def test_a_bystander_sees_the_listing(self, town: Any) -> None:
        """レナが出品すると、同席しているトムに届く。"""
        _drain_all(town)

        _list_bread(town, _LENA, quantity=2, price=20)

        observed = _market_observations(town, _TOM)
        assert len(observed) == 1
        assert "レナ" in observed[0].prose

    def test_the_listing_shows_what_and_for_how_much(self, town: Any) -> None:
        """観測には品名・個数・単価が入る。

        値が見えないと、値付けを見て自分の値を決めることができない。
        """
        _drain_all(town)

        _list_bread(town, _LENA, quantity=2, price=20)

        (observed,) = _market_observations(town, _TOM)
        assert _BREAD in observed.prose
        assert "20" in observed.prose
        assert observed.structured["unit_price"] == 20

    def test_the_lister_does_not_observe_their_own_listing(self, town: Any) -> None:
        """出した本人には届かない (結果文で分かる)。"""
        _drain_all(town)

        _list_bread(town, _LENA, quantity=1, price=20)

        assert _market_observations(town, _LENA) == []

    def test_it_is_social_and_does_not_wake_anyone(self, town: Any) -> None:
        """出品の観測は社会的な出来事で、誰の手番も起こさない。

        誰かが出品するたびに同席者全員の手番が起きると、行動密度が跳ね上がる。
        """
        _drain_all(town)

        _list_bread(town, _LENA, quantity=1, price=20)

        (observed,) = _market_observations(town, _TOM)
        assert observed.observation_category == "social"
        assert observed.schedules_turn is False

    def test_someone_far_from_the_board_sees_nothing(self, town: Any) -> None:
        """板から離れている人には届かない (正の対照)。"""
        _walk_away(town, _MINA)
        _drain_all(town)

        _list_bread(town, _LENA, quantity=1, price=20)

        assert _market_observations(town, _MINA) == []


class TestRepricingIsSeenByThoseAtTheBoard:
    """値の付け直しは、板の前に居る人に見える。

    **この実験でいちばん見たい出来事**。「価格が動的に変わる瞬間」がまさに
    ここで、場に居る人に見えないと値動きが社会的な出来事にならない。
    """

    def test_a_bystander_sees_the_price_move(self, town: Any) -> None:
        """レナが値を下げると、同席しているトムに届く。"""
        _list_bread(town, _LENA, quantity=2, price=20)
        _drain_all(town)

        town._market_service.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
        )

        observed = _market_observations(town, _TOM)
        assert len(observed) == 1

    def test_both_the_old_and_the_new_price_are_shown(self, town: Any) -> None:
        """旧値と新値の両方が出る。

        **「下げた」という方向が読めることに意味がある。** 新値だけだと、
        値が動いたのか最初からその値だったのかが区別できない。
        """
        _list_bread(town, _LENA, quantity=2, price=20)
        _drain_all(town)

        town._market_service.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
        )

        (observed,) = _market_observations(town, _TOM)
        assert "20" in observed.prose and "18" in observed.prose
        assert observed.structured["old_unit_price"] == 20
        assert observed.structured["unit_price"] == 18

    def test_the_owner_does_not_observe_their_own_move(self, town: Any) -> None:
        """値を変えた本人には届かない (結果文で分かる)。"""
        _list_bread(town, _LENA, quantity=1, price=20)
        _drain_all(town)

        town._market_service.reprice_order(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL, new_unit_price=18,
        )

        assert _market_observations(town, _LENA) == []


class TestASaleIsSeenByTheRoomAndBySeller:
    """約定は、その場の人にも、離れている売り手にも届く。"""

    def test_a_bystander_sees_who_bought_from_whom(self, town: Any) -> None:
        """買われたことが、売り手の名前つきで同席者に見える。

        **誰の値が受け入れられたか**が見えないと、値付けの巧拙が社会的に
        観測されない。
        """
        _list_bread(town, _LENA, quantity=1, price=18)
        _drain_all(town)

        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        (observed,) = _market_observations(town, _MINA)
        assert "トム" in observed.prose
        assert "レナ" in observed.prose
        assert "18" in observed.prose

    def test_the_seller_hears_about_it_from_far_away(self, town: Any) -> None:
        """売り手が板から離れていても、「売れた」が届く。

        板越しの取引なので、その場に居なくても自分の持ち物が変わったことを
        知る必要がある。届かないと、次に板へ寄るまで自分の状態が分からない。
        """
        _list_bread(town, _LENA, quantity=1, price=18)
        _walk_away(town, _LENA)
        _drain_all(town)

        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        observed = _market_observations(town, _LENA)
        assert len(observed) == 1
        assert "売れた" in observed[0].prose

    def test_the_sale_does_not_wake_the_seller(self, town: Any) -> None:
        """「売れた」は売り手の手番を起こさない。

        知って、次の自分の手番で動けばよい。
        """
        _list_bread(town, _LENA, quantity=1, price=18)
        _walk_away(town, _LENA)
        _drain_all(town)

        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        (observed,) = _market_observations(town, _LENA)
        assert observed.schedules_turn is False

    def test_the_buyer_does_not_observe_their_own_purchase(self, town: Any) -> None:
        """買った本人には届かない (結果文で分かる)。"""
        _list_bread(town, _LENA, quantity=1, price=18)
        _drain_all(town)

        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=1, current_tick=town.current_tick(),
        )

        assert _market_observations(town, _TOM) == []

    def test_crossing_two_listings_tells_both_sellers(self, town: Any) -> None:
        """2 人の出品にまたがって買うと、両方の売り手に届く。

        まとめて 1 件にすると、片方の売り手は自分の品が売れたことを知らない。
        """
        _list_bread(town, _LENA, quantity=1, price=18)
        _list_bread(town, _MINA, quantity=1, price=20)
        _walk_away(town, _LENA)
        _walk_away(town, _MINA)
        _drain_all(town)

        town._market_service.buy_best(
            _TOM, item_label=_BREAD, quantity=2, current_tick=town.current_tick(),
        )

        assert len(_market_observations(town, _LENA)) == 1
        assert len(_market_observations(town, _MINA)) == 1


class TestCancellingIsSeenByThoseAtTheBoard:
    """取り下げも、板の前に居る人に見える。"""

    def test_a_bystander_sees_the_withdrawal(self, town: Any) -> None:
        """出品が取り下げられると、同席者に届く。

        見えないと、さっきまであった選択肢が理由もなく消えたことになる。
        """
        _list_bread(town, _LENA, quantity=1, price=20)
        _drain_all(town)

        town._market_service.cancel_by(
            _LENA, item_label=_BREAD, side=MarketOrderSide.SELL,
        )

        observed = _market_observations(town, _TOM)
        assert len(observed) == 1
        assert "レナ" in observed[0].prose


class TestExpiryReachesItsOwnerWhereverTheyAre:
    """期限切れは、持ち主に届く。

    板から離れた場所に居ると、自分の出品が流れたことを知る手段が無い。次に
    板へ寄るまで、預けた品は板の上にあり、所持品からは消えたままになる。
    Phase 2 で「返事がないまま流れた」を当事者に届けると決めたのと同じ状況。
    """

    def test_the_owner_hears_that_it_came_back(self, town: Any) -> None:
        """引き取れたときは、「手元に戻った」が届く。"""
        order = _list_bread(town, _LENA, quantity=1, price=20)
        _walk_away(town, _LENA)
        _drain_all(town)

        town._market_service.expire_orders(current_tick=order.expires_at_tick + 1)

        observed = _market_observations(town, _LENA)
        assert len(observed) == 1
        assert "戻" in observed[0].prose

    def test_the_owner_hears_that_it_is_waiting(self, town: Any) -> None:
        """引き取れなかったときは、「板に残っている」が届く。

        **文面を状態で分ける。** 手元に戻ったのか、板で引き取りを待っている
        のかで、次の一手が違う (何もしなくてよい / 空けて引き取りに行く)。
        """
        order = _list_bread(town, _LENA, quantity=1, price=20)
        while not town._player_inventory_repo.find_by_id(_LENA).is_inventory_full():
            _give(town, _LENA, _HERB, 1)
        _drain_all(town)

        town._market_service.expire_orders(current_tick=order.expires_at_tick + 1)

        (observed,) = _market_observations(town, _LENA)
        assert "引き取" in observed.prose
        assert observed.structured["kind"] == "expired_awaiting"

    def test_it_does_not_wake_the_owner(self, town: Any) -> None:
        """期限切れは持ち主の手番を起こさない。"""
        order = _list_bread(town, _LENA, quantity=1, price=20)
        _drain_all(town)

        town._market_service.expire_orders(current_tick=order.expires_at_tick + 1)

        (observed,) = _market_observations(town, _LENA)
        assert observed.schedules_turn is False

    def test_bystanders_are_not_told(self, town: Any) -> None:
        """第三者には流さない (正の対照)。

        期限切れは Phase 2 の辞退・期限切れと同じく当事者だけの出来事で、
        毎回流すと板の前が通知で埋まる。
        """
        order = _list_bread(town, _LENA, quantity=1, price=20)
        _drain_all(town)

        town._market_service.expire_orders(current_tick=order.expires_at_tick + 1)

        assert _market_observations(town, _TOM) == []
