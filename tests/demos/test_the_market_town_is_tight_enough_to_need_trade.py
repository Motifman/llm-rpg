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
import re
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    get_spot_graph_specs,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
)

_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v3_board.json"
)

#: run の長さ。profile 側の設定なのでシナリオからは読めない。実験の標準値。
_RUN_TICKS = 80
#: 空腹の上限。これに触れると飢餓ダメージが始まる。
_HUNGER_LIMIT = 100

#: 鞄が満杯のときに、品を減らせる道。**定数から組む。**
#:
#: 文字列で書くと、存在しない名前が混ざっても気づけない。実在しない名前は
#: `disabled_tools` に入りようがない (`create_world_runtime` が落とす) ので、
#: 表に 1 つ混ざるだけで**この検査は何を落としても緑になる**。
_ESCAPES_FROM_A_FULL_BAG = frozenset({
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
})


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


def _harvests(scenario: Dict[str, Any], target: str) -> int:
    """再生間隔から出る、run 中の収穫回数の上限。"""
    binding = next(
        b for b in scenario["reactive_bindings"]["objects"]
        if b["target"] == target
    )
    return _RUN_TICKS // int(binding["predicate"]["ticks_offset"])


def _breads_producible(scenario: Dict[str, Any]) -> int:
    """材料の再生間隔から出る、パンの生産可能量の上限。

    v3.7 からパンは麦と薬草の両方を 1 つずつ使うので、**少ない方の材料が
    律速になる**。麦を刈れるのは 1 人・薬草の茂みは 1 つなので、上限は
    それぞれの再生間隔で決まる。移動時間は引いておらず、薬草は商人への
    換金とも取り合いになるので、**実際の生産量はこれより低い**。
    """
    oven = next(
        obj for spot in scenario["spots"]
        for obj in spot.get("interior", {}).get("objects", [])
        if obj["id"] == "stone_oven"
    )
    consumed = {
        e["parameters"]["item_spec"]
        for e in oven["interactions"][0]["effects"]
        if e["effect_type"] == "REMOVE_ITEM"
    }
    assert consumed == {"wheat", "herb"}, (
        f"石窯の材料が設計表 (麦 + 薬草) とずれています: {sorted(consumed)}"
    )
    loaves_per_batch = sum(
        1 for e in oven["interactions"][0]["effects"]
        if e["effect_type"] == "GIVE_ITEM" and e["parameters"]["item_spec"] == "bread"
    )
    batches = min(_harvests(scenario, "wheat_rows"), _harvests(scenario, "herb_patch"))
    return batches * loaves_per_batch


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

    def test_two_harvests_buy_bread_even_at_the_anchor(self, scenario) -> None:
        """薬草 2 本の稼ぎで、板の初期のいちばん高いパンが買える。

        v3 の交易条件は収奪的だった (入り 25G / 出 60G)。摘み手の稼ぎと
        パンの値の**スケールが乖離すると、買い手に金が無い世界に戻る**。
        初期注文の値は意図的に高い錨なので、そこと比べて成り立つなら、
        実勢 (実 run で 8〜17G) では確実に成り立つ。
        """
        herb = next(
            b["price"] for b in scenario["merchants"][0]["buys"]
            if b["item_spec"] == "herb"
        )
        dearest_bread = max(
            o["unit_price"] for o in scenario["market"]["initial_orders"]
            if o["item_spec"] == "bread" and o["side"] == "sell"
        )

        assert herb * 2 >= dearest_bread


class TestTheWorldDoesNotLieAboutItsPrices:
    """世界の中の掲示 (木札) と、実際の値が一致している。"""

    def test_the_sign_shows_the_prices_the_merchant_actually_uses(
        self, scenario,
    ) -> None:
        """木札に書かれた値が、商人の宣言と一致する。

        **値を動かして木札を忘れると、世界が嘘をつく。** エージェントは
        木札を読んで判断するので、失敗の原因が「嘘を信じた」になり、
        trace から追うのが極めて難しくなる。

        **品ごとに突き合わせる。** 「その値が木札のどこかに出てくる」だけ
        だと、2 つの値がたまたま同じとき (いまの 10G と 10G) に、品と値の
        取り違えを見逃す。実際、最初に書いた検査はこの形で、木札を古い値の
        まま残す変異を素通りさせた。
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
        names = {spec["id"]: spec["name"] for spec in scenario["item_specs"]}
        merchant = scenario["merchants"][0]
        posted = dict(re.findall(r"『(\S+?)\s*(?:買取|売値)\s*(\d+)G』", sign))

        expected = {
            names[entry["item_spec"]]: str(entry["price"])
            for entry in merchant["buys"] + merchant["sells"]
        }
        assert posted == expected


class TestTheTownOnlyOffersToolsItCanUse:
    """この町で使い道の無いツールは、そもそも出さない。"""

    def test_tools_with_nothing_to_act_on_are_disabled(self, scenario) -> None:
        """探索と聞き耳を落としている。

        v3 / v3.1 の実 run で `listen` は 0 回、`explore` は 5 回だが、
        **隠しオブジェクトもサブ場所も 1 つも無い**ので探すものが無い。
        ツール定義はプロンプトの 3 分の 2 を占める固定費なので、使い道の
        無いものを出し続けるのは高い。
        """
        assert {"listen", "explore"} <= set(scenario["disabled_tools"])

    def test_there_really_is_nothing_to_explore(self, scenario) -> None:
        """探索で見つかるものが、実際に 1 つも無い (**正の対照**)。

        隠しオブジェクトやサブ場所を後から足した人が `explore` を落とした
        ままにすると、**そこへ到達する手段が無い世界**ができる。
        """
        hidden = [
            obj for spot in scenario["spots"]
            for obj in spot.get("interior", {}).get("objects", [])
            if not obj.get("is_visible", True)
        ]
        sub_locations = [
            sub for spot in scenario["spots"]
            for sub in spot.get("interior", {}).get("sub_locations", [])
        ]

        assert hidden == []
        assert sub_locations == []

    def test_the_way_out_of_a_full_bag_is_kept(self, scenario) -> None:
        """満杯から抜ける道が、**どれか 1 つは**残っている。

        以前はここで `drop_item` を名指しで固定していた。理由は 2 つあって、
        どちらも道具そのものではなく**性質**を守るためだった。

        1. 満杯の助言が「相手が drop するのを待て」と道具名を書いていた
           (助言側は #1204 で道具名を書かない文に直っている)
        2. 満杯からの回復手段が尽きると、#1179 / #1183 で塞いだ穴が別の形で開く

        v3.4 で贈与と同席取引を落としたので、名指しの固定は「この町では
        使えない道具を残せ」という指示に化けた。**守りたかった性質のほうを
        書く。**

        脱出路の名前は**文字列で書かない**。最初にこれを書いたとき
        ``"sell"`` という**存在しないツール名**を混ぜてしまい、実在しない
        名前は `disabled_tools` に入りようがないので、**この検査は何を
        落としても緑になる**状態だった。表で守る検査に実在しない行が 1 つ
        混ざると、表は空にならない。
        """
        disabled = set(scenario["disabled_tools"])

        assert _ESCAPES_FROM_A_FULL_BAG - disabled, (
            "満杯から抜ける道が 1 つも残っていません: "
            f"{sorted(_ESCAPES_FROM_A_FULL_BAG)} がすべて disabled_tools に"
            "入っています"
        )

    def test_every_escape_route_is_a_tool_that_exists(self) -> None:
        """脱出路の表に、**実在するツールしか載っていない** (**正の対照**)。

        定数から組んでも、定数の中身が古くなれば同じ穴が開く。実在しない
        名前は `disabled_tools` に入りようがないので、**表に 1 つ混ざるだけ
        で上の検査は何を落としても緑になる**。表が空でないことも併せて見る。
        """
        known = {defn.name for defn, _ in get_spot_graph_specs()}

        assert _ESCAPES_FROM_A_FULL_BAG
        assert _ESCAPES_FROM_A_FULL_BAG <= known
        assert TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM in known

    def test_what_the_board_hands_over_can_still_be_picked_up(
        self, scenario
    ) -> None:
        """`pickup_item` は落とさない。

        板の受け渡しは、買い手の鞄が満杯なら**品を板のある広場の地面へ
        置く** (`board_delivery_overflow_sink`)。拾えなくすると、**代金を
        払ったのに品が永久に取り出せない**。

        贈与を落としても地面渡しが閉じるだけだが、`pickup_item` を落とすと
        **板そのものが壊れる**。
        """
        assert TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM not in scenario["disabled_tools"]


class TestThereIsRoomToPlaceABid:
    """買い注文を出せるだけの余裕が、買う側 (焼き手) にある。

    v3.7 で買い注文の主役は摘み手から焼き手に移った。焼き手は麦と薬草の
    両方を自分の外から仕入れるしかなく、**仕入れられなければ町のパンが
    止まる**。買い注文は gold を先に預けるので、預けられる金が無いと
    `market_bid` は構造的に出ない (v3〜v3.6 の摘み手側で実証済み)。
    """

    def test_a_baker_can_outbid_every_declared_herb_floor(self, scenario) -> None:
        """焼き手の持ち金が、薬草の宣言済みのどの買値よりも高い。

        摘み手には「商人に売れば確実に 14G」という下限があるので、焼き手が
        薬草を仕入れるには**それを上回る値を付けられる**必要がある。持ち金が
        下限以下だと、焼き手は初手から詰んでいて、buy 板は一生立たない。
        """
        stall_floor = next(
            b["price"] for b in scenario["merchants"][0]["buys"]
            if b["item_spec"] == "herb"
        )
        board_floor = max(
            o["unit_price"] for o in scenario["market"]["initial_orders"]
            if o["item_spec"] == "herb" and o["side"] == "buy"
        )
        baker_gold = [
            p["initial_gold"] for p in scenario["players"]
            if p["initial_state"]["trade"] == "baker"
        ]

        assert baker_gold, "焼き手が 1 人も居ない (検査が空振りする)"
        assert all(g > max(stall_floor, board_floor) for g in baker_gold)

    def test_a_baker_can_fund_a_whole_first_batch(self, scenario) -> None:
        """焼き手の持ち金で、初回の一窯 (麦 1 + 薬草 1) が賄える。

        薬草側の実勢の下限は商人の買取 (14G)。麦には宣言済みの下限が無い
        ので、過去 run の実勢ではなく**薬草と同じ下限まで払う**と置いて
        見積もる。ここが賄えないと、焼き手は売るものが作れず、**売って
        から仕入れる**という循環の入口が無い。
        """
        stall_floor = next(
            b["price"] for b in scenario["merchants"][0]["buys"]
            if b["item_spec"] == "herb"
        )
        baker_gold = [
            p["initial_gold"] for p in scenario["players"]
            if p["initial_state"]["trade"] == "baker"
        ]

        assert baker_gold, "焼き手が 1 人も居ない (検査が空振りする)"
        assert all(g >= stall_floor * 2 for g in baker_gold)
