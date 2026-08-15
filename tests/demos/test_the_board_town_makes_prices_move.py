"""掲示板のある市場町で、値が動く条件がそろっている (経済統合 Phase 3、PR 4)。

**設計表をそのままテストに置く。** 実装に対して書くと、実装が表とずれていても
緑になる (v2.0 で職能表が一度も実装されないまま 18 件が緑だった)。

この町が観察しようとしているのは 2 種類の力である。

| 品 | 作り手 | 競うのは | 値が動く向き |
|---|---|---|---|
| 薬草 | 摘み手 2 人 | **売り手同士** | 下がる |
| パン | 焼き手 2 人 | **売り手同士** | 下がる |
| 麦束 | 畑の人 1 人 | **買い手同士** (焼き手 2 人) | 上がる |

上下両方の力が同じ run に入っている。買い板を入れた判断がここで効いている。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Tuple

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_TOWN = (
    pathlib.Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v3_board.json"
)

_LENA, _KAI, _TOM, _NORA, _MINA = (PlayerId(i) for i in range(1, 6))

#: 職能の設計表。**行 = 人、列 = 仕事、値 = できるか。**
#: 表を写すので、実装を見ずに書ける。
_JOB_MATRIX: Dict[str, Dict[str, bool]] = {
    "レナ":  {"gather_herb": True,  "bake_bread": False, "reap_wheat": False},
    "カイ":  {"gather_herb": True,  "bake_bread": False, "reap_wheat": False},
    "トム":  {"gather_herb": False, "bake_bread": True,  "reap_wheat": False},
    "ノラ":  {"gather_herb": False, "bake_bread": True,  "reap_wheat": False},
    "ミナ":  {"gather_herb": False, "bake_bread": False, "reap_wheat": True},
}

#: 仕事ごとの (作業場, 対象オブジェクト)。
_WORK: Dict[str, Tuple[str, str]] = {
    "gather_herb": ("herb_slope", "herb_patch"),
    "bake_bread": ("bake_house", "stone_oven"),
    "reap_wheat": ("wheat_field", "wheat_rows"),
}

_NAME_TO_ID = {"レナ": _LENA, "カイ": _KAI, "トム": _TOM, "ノラ": _NORA, "ミナ": _MINA}


class _Town:
    """v3 の町を立て、実経路でツールを叩く。"""

    def __init__(self) -> None:
        self.runtime = create_world_runtime(str(_TOWN))
        self.raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))

    def spot_of(self, player_id: PlayerId):
        graph = self.runtime._spot_graph_repo.find_graph()
        return graph.get_entity_spot(EntityId.create(int(player_id)))

    def spot_id(self, string_id: str):
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId

        return SpotId.create(self.runtime.id_mapper.get_int("spot", string_id))

    def place(self, player_id: PlayerId, string_id: str) -> None:
        graph = self.runtime._spot_graph_repo.find_graph()
        entity = EntityId.create(int(player_id))
        graph.unplace_entity(entity)
        graph.place_entity(entity, self.spot_id(string_id))
        self.runtime._spot_graph_repo.save(graph)

    def give(self, player_id: PlayerId, item_id: str, count: int = 1) -> None:
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            grant_item_specs_to_inventory,
        )
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
        from tests.support.overflow_sinks import IGNORE_OVERFLOW

        spec_id = self.runtime.id_mapper.get_int("item_spec", item_id)
        grant_item_specs_to_inventory(
            player_id,
            tuple(ItemSpecId.create(spec_id) for _ in range(count)),
            self.runtime._item_repo,
            self.runtime._item_spec_repo,
            self.runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )

    def try_work(self, player_id: PlayerId, object_id: str, action: str):
        """働きかけを試し、(できたか, 断り文) を返す。

        前提を満たさない働きかけは**例外**で返る。表の「できるか」を確かめる
        には、成功と拒否を同じ形に揃える必要がある。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )

        try:
            result = self.interact(player_id, object_id, action)
        except InteractionNotAllowedException as exc:
            return False, str(exc)
        return bool(getattr(result, "success", True)), str(
            getattr(result, "message", "")
        )

    def interact(self, player_id: PlayerId, object_id: str, action: str):
        """作業場のオブジェクトへ働きかける (実サービス経由)。"""
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.world_graph.value_object.spot_object_id import (
            SpotObjectId,
        )

        return self.runtime._interaction_service.execute_interaction(
            player_id,
            SpotObjectId.create(self.runtime.id_mapper.get_int("object", object_id)),
            action,
            current_tick=WorldTick(self.runtime.current_tick()),
        )

    def travel_ticks(self, frm: str, to: str) -> int:
        """実際に道をたどって手番数を測る。**表に書いた数字を写さない。**"""
        graph = self.runtime._spot_graph_repo.find_graph()
        start, goal = self.spot_id(frm), self.spot_id(to)
        for conn in graph.iter_outgoing_connections_from(start):
            if conn.to_spot_id == goal:
                return conn.travel_ticks
        raise AssertionError(f"{frm} から {to} への道がない")

    def has_direct_road(self, frm: str, to: str) -> bool:
        graph = self.runtime._spot_graph_repo.find_graph()
        return any(
            conn.to_spot_id == self.spot_id(to)
            for conn in graph.iter_outgoing_connections_from(self.spot_id(frm))
        )


@pytest.fixture()
def town() -> _Town:
    return _Town()


class TestOnlyItsOwnerCanDoEachJob:
    """職能の表を、総当たりでそのまま確かめる。"""

    @pytest.mark.parametrize("who", sorted(_JOB_MATRIX))
    @pytest.mark.parametrize("job", sorted(_WORK))
    def test_the_matrix_holds(self, town: _Town, who: str, job: str) -> None:
        """表のとおりに、できる人だけができる。

        **できないことを確かめるときは、別の理由で落ちていないかを切り分ける。**
        材料不足で落ちているのを職能の壁と読み違えないよう、要る材料は先に
        持たせてから叩く (#1174 の教訓)。
        """
        player_id = _NAME_TO_ID[who]
        spot, target = _WORK[job]
        town.place(player_id, spot)
        if job == "bake_bread":
            town.give(player_id, "wheat", 1)

        did, message = town.try_work(player_id, target, job)

        assert did is _JOB_MATRIX[who][job], (
            f"{who} が {job} を {'できる' if _JOB_MATRIX[who][job] else 'できない'} "
            f"はずだが、結果は {did} ({message})"
        )

    @pytest.mark.parametrize("who", ["トム", "ノラ", "ミナ"])
    def test_the_refusal_says_it_is_not_your_work(self, town: _Town, who: str) -> None:
        """断り文が「自分の仕事ではない」と読める。

        「材料が無い」と読めると、集めればできると思って手番を溶かす。
        """
        player_id = _NAME_TO_ID[who]
        town.place(player_id, "herb_slope")

        did, message = town.try_work(player_id, "herb_patch", "gather_herb")

        assert did is False
        assert "あの人だけ" in message or "見分け" in message


class TestTwoMakersForTheItemsThatShouldCompete:
    """競争のある品と無い品が、意図どおりに分かれている。"""

    def test_two_people_can_gather_herbs(self, town: _Town) -> None:
        """薬草の作り手は 2 人 (**売り手同士が競う**)。"""
        makers = [w for w, jobs in _JOB_MATRIX.items() if jobs["gather_herb"]]

        assert len(makers) == 2

    def test_two_people_can_bake_bread(self, town: _Town) -> None:
        """パンの作り手も 2 人。"""
        makers = [w for w, jobs in _JOB_MATRIX.items() if jobs["bake_bread"]]

        assert len(makers) == 2

    def test_only_one_person_can_reap_wheat(self, town: _Town) -> None:
        """麦の作り手は 1 人 (**買い手同士が競う**、かつ競争の無い対照)。

        焼き手 2 人が同じ麦を欲しがるので、麦では値が**上がる**方向の力が
        働く。薬草・パンの下がる力と対になる。
        """
        makers = [w for w, jobs in _JOB_MATRIX.items() if jobs["reap_wheat"]]
        bakers = [w for w, jobs in _JOB_MATRIX.items() if jobs["bake_bread"]]

        assert len(makers) == 1
        assert len(bakers) == 2


class TestTheWorkshopsAreNotJoinedToEachOther:
    """作業場同士は道で繋がっていない。"""

    @pytest.mark.parametrize(
        "frm,to",
        [
            ("herb_slope", "bake_house"),
            ("herb_slope", "wheat_field"),
            ("bake_house", "wheat_field"),
            ("bake_house", "herb_slope"),
            ("wheat_field", "herb_slope"),
            ("wheat_field", "bake_house"),
        ],
    )
    def test_there_is_no_direct_road(self, town: _Town, frm: str, to: str) -> None:
        """作業場から作業場への直通路が無い。

        **これが「板へ置いて帰る」を最短にする構造。** 繋がっていると、
        持って行って直接渡す方が安くなり、板を使う理由が薄れる。
        """
        assert town.has_direct_road(frm, to) is False

    @pytest.mark.parametrize("workshop", ["herb_slope", "bake_house", "wheat_field"])
    def test_every_workshop_reaches_the_square(self, town: _Town, workshop: str) -> None:
        """どの作業場からも広場へは戻れる (**正の対照**)。

        繋がなさすぎると町として成立しない。
        """
        assert town.has_direct_road(workshop, "market_square") is True


class TestLeavingItOnTheBoardIsCheaperThanWaiting:
    """板へ置いて帰る方が、相手を待つより安い。"""

    def test_the_producer_round_trip_is_short(self, town: _Town) -> None:
        """畑の人の往復は、実際に歩いて 4 手番。

        広場 → 畑 (2) → 刈る → 畑 → 広場 (2)。板へ出すのがさらに 1 手番で、
        **5 手番で仕事が閉じる**。
        """
        out = town.travel_ticks("market_square", "wheat_field")
        back = town.travel_ticks("wheat_field", "market_square")

        assert out + back == 4

    def test_handing_over_in_person_needs_the_other_to_be_there(
        self, town: _Town
    ) -> None:
        """直接渡すには、相手が広場に居合わせる必要がある。

        作業場同士が繋がっていないので、畑の人が窯へ持って行くこともできない。
        **待つか、板へ置くかの二択**になっていることを、道の形から確かめる。
        """
        assert town.has_direct_road("wheat_field", "bake_house") is False
        assert town.has_direct_road("wheat_field", "market_square") is True


class TestTheBoardStartsWithTwoPricesForTheSameItem:
    """板は、同じ品に別々の値が並んだ状態で始まる。"""

    def test_bread_has_two_different_prices(self, town: _Town) -> None:
        """パンの売り注文が、別々の値で 2 件出ている。

        **初手から値の比較が発生する**。1 件だけだと、比べる相手が居ない。
        """
        prices = sorted(
            order.unit_price_gold
            for order in town.runtime._market_service.board().orders
            if order.side.value == "sell"
        )

        assert len(prices) == 2
        assert prices[0] != prices[1]

    def test_the_board_price_differs_from_the_stall(self, town: _Town) -> None:
        """板の値は、屋台の値とずらしてある。

        同じ値だと屋台と板で同じ取引ができ、**板を使う理由が消える**。

        値そのものではなく**関係**を見る。以前は屋台の 6G を直接書いていたが、
        交易条件をまとめて動かしたときに、守りたい関係 (ずれていること) は
        保たれたまま落ちた。**値を書くと、値を動かすたびに落ちる。**
        """
        stall_buys = {
            entry["item_spec"]: entry["price"]
            for entry in town.raw["merchants"][0]["buys"]
        }
        board_bids = [
            order
            for order in town.runtime._market_service.board().orders
            if order.side.value == "buy"
        ]

        assert board_bids, "板に買い注文が 1 件も無い (ずれの検査が空振りする)"
        assert all(
            order.unit_price_gold != stall_buys["herb"] for order in board_bids
        )

    def test_the_stall_does_not_sell_bread(self, town: _Town) -> None:
        """屋台はパンを扱わない (板と品目で棲み分ける)。"""
        stall_sells = {
            entry["item_spec"] for entry in town.raw["merchants"][0]["sells"]
        }

        assert "bread" not in stall_sells


class TestHowSoonThePriceCanMove:
    """値が動くまでの最短手番を、地図から組み立てて数える。

    **理想的に動いたときの下限**を出す。エージェントが最短で動き、各自の手番は
    並行に進むと仮定する。実際は探索・会話・失敗が挟まるので、これは
    「run 長がこれを下回ったら**構造的に不可能**」という下限として使う。

    2 つに分けて数える。

    - **担保 (パン)**: 初期注文が別々の値で 2 件あるので、買うだけで異なる
      単価の約定が 2 回起きる。run が「値の動きを 1 つも観測できずに終わる」
      ことがないことの保証
    - **本命 (薬草)**: 摘み手 2 人が自分で値を付け、それぞれが売れる。
      **エージェントが決めた値**が約定に現れるまで
    """

    def _round_trip(self, town: _Town, workshop: str) -> int:
        """広場から作業場を往復する手番数 (実際に道をたどって測る)。"""
        return (
            town.travel_ticks("market_square", workshop)
            + town.travel_ticks(workshop, "market_square")
        )

    def test_the_guaranteed_path_is_two_ticks(self, town: _Town) -> None:
        """担保の経路は 2 手番。

        パンの売り注文が 24G と 20G で並んでいるので、広場に居る者が
        **買うだけ**で異なる単価の約定が 2 回起きる (1 回の買いが 1 手番)。
        """
        prices = sorted(
            order.unit_price_gold
            for order in town.runtime._market_service.board().orders
            if order.side.value == "sell"
        )
        assert len(prices) == 2 and prices[0] != prices[1]

        guaranteed_ticks = len(prices)  # 1 件につき 1 手番の買い

        assert guaranteed_ticks == 2

    def test_the_main_path_fits_well_inside_a_run(self, town: _Town) -> None:
        """本命の経路も、80 手番に十分収まる。

        摘み手 2 人が**並行に**動くので、往復は 1 人ぶんで数える。

            広場 → 土手 → 摘む → 土手 → 広場 → 出品   = 往復 + 2
            (2 人目も同じだけかかるが、同時に進む)
            買い手が 1 回目を買う                      = +1
            買い手が 2 回目を買う (別の値)             = +1
        """
        round_trip = self._round_trip(town, "herb_slope")
        gather_and_list = round_trip + 2  # 摘む 1 + 出品 1
        two_settlements = 2

        main_ticks = gather_and_list + two_settlements

        assert main_ticks <= 80, (
            f"本命の経路が {main_ticks} 手番かかり、run 長 80 に収まらない"
        )
        # 見積もりを固定して、地図をいじったときに気づけるようにする。
        assert main_ticks == 8

    def test_the_baker_loop_also_fits(self, town: _Town) -> None:
        """麦 → パンの一巡も 80 手番に収まる。

        **買い手同士の競争 (麦) が見えるまで**の経路。畑の人が麦を板へ出し、
        焼き手 2 人がそれを取り合う。
        """
        reap = self._round_trip(town, "wheat_field") + 2   # 刈る 1 + 出品 1
        bake = 1 + self._round_trip(town, "bake_house") + 1  # 買う 1 + 往復 + 焼く 1
        sell_bread = 1

        baker_loop = reap + bake + sell_bread

        assert baker_loop <= 80
        assert baker_loop == 13

    def test_the_workshops_are_what_make_the_loop_long(self, town: _Town) -> None:
        """一巡の長さは、作業場の往復で決まっている (**正の対照**)。

        道を短くすれば一巡も短くなる、という関係が成立していることを見る。
        地図をいじったのに数字が動かないなら、測っているものが違う。
        """
        assert self._round_trip(town, "herb_slope") == 4
        assert self._round_trip(town, "wheat_field") == 4
        assert self._round_trip(town, "bake_house") == 4
