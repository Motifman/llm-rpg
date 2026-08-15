"""市場町の値と厳しさが、市場が要る世界になっていることを保証する。

## なぜこの試験が要るか

v3 の run では **80 手番 × 空腹 +1 = 最大 80 で、上限 100 に届く経路が存在
しなかった**。パンの必要量は 0 個で、全員が**必要がないのに食べていた**。
市場が回らなかった直接の原因は「贈与で足りた」ではなく「**そもそも要らなかった**」。

数値どうしの**関係**が崩れると、同じ世界がまた出来上がる。しかも run を回すまで
気づけない (1 回 80 手番の実 LLM run)。だからここでは個々の値ではなく、
**値どうしが満たすべき関係**を見る。

見るのは 3 つ。

1. **足りない**: 全員ぶんのパンを作るには町の生産がぎりぎり足りない
2. **詰まない**: それでも生産可能量を超えない
3. **板を通る理由がある**: 板の買値が屋台の買値より高い
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict

import pytest

_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v3_board.json"
)

#: run の長さ。profile 側の設定なのでシナリオからは読めない。実験の標準値。
_RUN_TICKS = 80
#: 空腹の上限。これに触れると飢餓ダメージが始まる。
_HUNGER_LIMIT = 100


@pytest.fixture(scope="module")
def scenario() -> Dict[str, Any]:
    return json.loads(_SCENARIO.read_text(encoding="utf-8"))


def _hunger_per_tick(scenario: Dict[str, Any]) -> int:
    return int(scenario["needs"]["hunger_per_tick"])


def _bread_restores(scenario: Dict[str, Any]) -> int:
    bread = next(s for s in scenario["item_specs"] if s["id"] == "bread")
    return int(bread["consume_effect"][0]["amount"])


def _breads_needed(scenario: Dict[str, Any]) -> int:
    """全員が上限に触れないために食べるパンの総数。

    1 人あたりの許容量は上限の 1 手前まで。そこを超えるぶんをパンで戻す。
    """
    accrued = _RUN_TICKS * _hunger_per_tick(scenario)
    per_person = max(0, math.ceil((accrued - (_HUNGER_LIMIT - 1))
                                  / _bread_restores(scenario)))
    return per_person * len(scenario["players"])


def _breads_producible(scenario: Dict[str, Any]) -> int:
    """麦の再生間隔から出る、パンの生産可能量の上限。

    麦を刈れるのは 1 人だけなので、上限は再生間隔で決まる。移動時間は
    引いていないので、**実際の生産量はこれより低い**。
    """
    binding = next(
        b for b in scenario["reactive_bindings"]["objects"]
        if b["target"] == "wheat_rows"
    )
    regrow = int(binding["predicate"]["ticks_offset"])
    oven = next(
        obj for spot in scenario["spots"]
        for obj in spot.get("interior", {}).get("objects", [])
        if obj["id"] == "stone_oven"
    )
    loaves_per_wheat = sum(
        1 for e in oven["interactions"][0]["effects"]
        if e["effect_type"] == "GIVE_ITEM" and e["parameters"]["item_spec"] == "bread"
    )
    return (_RUN_TICKS // regrow) * loaves_per_wheat


class TestThereIsNotEnoughBreadToGoAround:
    """パンが余らない。**余っている限り、気前よさにコストが無い。**"""

    def test_everyone_has_to_eat_at_least_once(self, scenario) -> None:
        """空腹が上限に届くので、パンを食べないと済まない。

        v3 はここが 0 個だった。**必要量が 0 の世界では、市場は要らない。**
        """
        assert _breads_needed(scenario) > 0

    def test_the_town_cannot_comfortably_feed_itself(self, scenario) -> None:
        """必要量が生産可能量の 7 割を超える (= 余剰が小さい)。

        余剰が大きいと、贈与が無料のままになり市場が要らない構造が残る。
        生産可能量は移動時間を引いていない上限なので、**実際にはもっと
        きつい**。
        """
        needed, producible = _breads_needed(scenario), _breads_producible(scenario)

        assert needed / producible > 0.7


class TestButTheTownIsNotDoomed:
    """詰まない。**生存の検証ではなく、生活の検証にする。**"""

    def test_the_need_stays_within_what_can_be_produced(self, scenario) -> None:
        """必要量が生産可能量を超えない。

        超えると、どうやっても足りない世界になる。観察したいのは
        やりくりであって、餓死ではない。
        """
        assert _breads_needed(scenario) <= _breads_producible(scenario)

    def test_reaching_the_limit_does_not_kill_within_the_run(self, scenario) -> None:
        """上限に達しても、run が終わるまでに死なない (**安全弁**)。

        最短でも上限到達は run の途中なので、残り手番ぶんのダメージが
        体力を超えないことを見る。ここが崩れると、値の調整が
        「苦しいが死なない」から「死ぬ」に変わる。
        """
        ticks_to_limit = _HUNGER_LIMIT // _hunger_per_tick(scenario)
        damage = (_RUN_TICKS - ticks_to_limit) * int(
            scenario["needs"]["starvation_damage_per_tick"]
        )

        assert damage < 100


class TestTheBoardIsWorthUsing:
    """板を通る理由が残っている。"""

    def test_the_board_pays_more_for_herbs_than_the_stall(self, scenario) -> None:
        """板の買い注文が、屋台の買取より高い。

        逆転すると**板で薬草を売る理由が消える**。v3 で `market_sell` が
        使われたのは、板の方が 1G 高かったから。値をまとめて動かすときに
        いちばん壊れやすい関係なので、値そのものではなく**関係**を見る。
        """
        stall = next(
            b["price"] for b in scenario["merchants"][0]["buys"]
            if b["item_spec"] == "herb"
        )
        board = next(
            o["unit_price"] for o in scenario["market"]["initial_orders"]
            if o["item_spec"] == "herb" and o["side"] == "buy"
        )

        assert board > stall

    def test_a_picker_can_afford_wheat_after_one_harvest(self, scenario) -> None:
        """薬草 1 本を売れば、麦 1 束が買える。

        v3 は 薬草 6〜7G に対し麦 15G で、**2.5 本摘まないと 1 束買えな
        かった**。摘み手の金が全部麦に消える構造がここから来ていた。
        """
        herb = next(
            b["price"] for b in scenario["merchants"][0]["buys"]
            if b["item_spec"] == "herb"
        )
        wheat = next(
            s["price"] for s in scenario["merchants"][0]["sells"]
            if s["item_spec"] == "wheat"
        )

        assert herb >= wheat


class TestTheWorldDoesNotLieAboutItsPrices:
    """世界の中の掲示 (木札) と、実際の値が一致している。"""

    def test_the_sign_shows_the_prices_the_merchant_actually_uses(
        self, scenario,
    ) -> None:
        """木札に書かれた値が、商人の宣言と一致する。

        **値を動かして木札を忘れると、世界が嘘をつく。** エージェントは
        木札を読んで判断するので、失敗の原因が「嘘を信じた」になり、
        trace から追うのが極めて難しくなる。
        """
        sign = next(
            effect["parameters"]["message"]
            for spot in scenario["spots"]
            for obj in spot.get("interior", {}).get("objects", [])
            for interaction in obj.get("interactions", [])
            for effect in interaction["effects"]
            if effect["effect_type"] == "SHOW_MESSAGE"
            and "木札" in effect["parameters"].get("message", "")
        )
        merchant = scenario["merchants"][0]

        for price in (merchant["buys"][0]["price"], merchant["sells"][0]["price"]):
            assert f"{price}G" in sign
