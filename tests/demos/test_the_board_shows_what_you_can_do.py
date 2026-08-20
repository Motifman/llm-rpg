"""板の表示は「自分が何をできるか」で書く (経済統合 Phase 3)。

「売り 3 件 (最安 18G)」の形は、読んだ人が「買い 1 件」を過去の約定か未来の
意思表示か取り違えた。**人間が迷う文面はエージェントも迷う**ので、行動の言葉に
寄せる。

利点は 3 つ。(1) 次に打つ手がそのまま文になる — 「18G で買える」から
`market_buy` が直接浮かび、板の状態を自分の行動へ翻訳する一段が要らない。
(2) 表示された数字が常に「自分が払う額」なので、売り手視点と買い手視点の混線が
起きない。(3) 値が交差していれば一目で分かる。

**買い側の列はこの PR では出さない。** 売る手段 (`market_sell`) がまだ無いのに
「15G で売れる」と書くと、存在しないツールを宣伝することになる
(`tend_to_player` / `give_item` で実際に起きた形)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_TOWN = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_MINA = PlayerId(3)
_BREAD = "焼きたてのパン"
_HERB = "薬草"


def _build(tmp_path: Path, *, with_market: bool = True) -> Any:
    raw: Dict[str, Any] = json.loads(_TOWN.read_text(encoding="utf-8"))
    spawn = raw["players"][0]["spawn_spot"]
    for pid, name in (("tom", "トム"), ("mina", "ミナ")):
        raw["players"].append({
            "id": pid, "name": name, "spawn_spot": spawn,
            "initial_items": [], "initial_gold": 300,
            "persona_prompt": f"あなたは{name}。",
        })
    if with_market:
        raw["players"][0]["initial_gold"] = 300
        raw["market"] = {"board_spot": "market_square"}
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


@pytest.fixture()
def town(tmp_path: Path) -> Any:
    return _build(tmp_path)


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


def _list_bread(runtime: Any, seller: PlayerId, *, quantity: int, price: int) -> Any:
    _give(runtime, seller, _BREAD, quantity)
    return runtime._market_service.place_sell_order(
        seller, item_label=_BREAD, quantity=quantity, unit_price=price,
        current_tick=runtime.current_tick(),
    )


def _state(runtime: Any, player_id: PlayerId) -> str:
    """その人の「現在の状況」を組み立てて文字列で返す。"""
    return runtime.build_full_prompt(player_id)["messages"][1]["content"]


def _board(runtime: Any, player_id: PlayerId) -> str:
    """その人が `market_view` で読む板の全文を返す。

    板はプロンプトに常駐しなくなったので、需給の文言の出所はツールの戻り値
    になった。ここで見るのは**文言そのもの**で、ツール呼び出しの実経路と
    場所の制限は `test_paying_a_turn_to_read_the_board.py` が見ている。
    """
    from ai_rpg_world.application.llm.services.market_board_text import (
        market_board_text,
    )

    service = runtime._market_service
    return market_board_text(
        service.board_view_for(player_id), service.item_display_name
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


class TestTheBoardIsShownInTheWordsOfWhatYouCanDo:
    """品揃えは「〜で買える」の形で出る。"""

    def test_a_listing_reads_as_something_you_can_buy(self, town: Any) -> None:
        """出品されている品は「18G で買える」と読める。"""
        _list_bread(town, _LENA, quantity=3, price=18)

        state = _board(town, _TOM)

        assert "18G で買える" in state
        assert _BREAD in state

    def test_the_number_of_listings_is_shown(self, town: Any) -> None:
        """出品の件数が出る。

        競争の激しさ (4 件も出ている = 下げないと売れない) を読む材料になる。
        """
        _list_bread(town, _LENA, quantity=1, price=18)
        _list_bread(town, _MINA, quantity=1, price=20)

        assert "出品 2件" in _board(town, _TOM)

    def test_the_cheapest_price_is_the_one_shown(self, town: Any) -> None:
        """出ている中でいちばん安い値が出る (それが実際に買える値)。"""
        _list_bread(town, _LENA, quantity=1, price=25)
        _list_bread(town, _MINA, quantity=1, price=18)

        state = _board(town, _TOM)

        assert "18G で買える" in state
        assert "25G で買える" not in state

    def test_the_sell_side_is_not_shown_yet(self, town: Any) -> None:
        """「売れる」は出さない。

        **売る手段がまだ無い。** 出すと、存在しないツールを本文が宣伝する
        形になり、無効化しないより悪い状態になる。
        """
        _list_bread(town, _LENA, quantity=1, price=18)

        assert "で売れる" not in _board(town, _TOM)

    def test_your_own_listing_is_not_offered_to_you(self, town: Any) -> None:
        """自分の出品は「買える」に数えない。

        自分の注文は自分で受けられないので、買えない値を相場として読ませない。
        """
        _list_bread(town, _LENA, quantity=1, price=18)

        state = _board(town, _LENA)

        assert "18G で買える" not in state


class TestYourOwnOrdersAreListedSeparately:
    """自分の注文は、別の行に 1 件ずつ出る。"""

    def test_your_listing_is_shown_with_its_price(self, town: Any) -> None:
        """自分の出品が、品名・残数・単価つきで出る。

        値を変える・取り下げるときの引数を、この行から組み立てる。
        """
        _list_bread(town, _LENA, quantity=2, price=20)

        state = _state(town, _LENA)

        assert "あなたの出品" in state
        assert _BREAD in state
        assert "20G" in state

    def test_an_unsold_listing_says_so(self, town: Any) -> None:
        """まだ売れていないことが書いてある。

        値下げの判断材料になる。
        """
        _list_bread(town, _LENA, quantity=2, price=20)

        assert "まだ売れていない" in _state(town, _LENA)

    def test_an_order_awaiting_collection_says_so(self, town: Any) -> None:
        """引き取り待ちの注文は、その状態つきで持ち主に出る。

        期限切れの通知を 1 回見落とした時点で取り戻す手がかりが消えるのを
        防ぐ最後の砦。
        """
        order = _list_bread(town, _LENA, quantity=1, price=20)
        while not town._player_inventory_repo.find_by_id(_LENA).is_inventory_full():
            _give(town, _LENA, _HERB, 1)
        town._market_service.expire_orders(current_tick=order.expires_at_tick + 1)

        assert "引き取り待ち" in _state(town, _LENA)

    def test_someone_elses_listing_is_not_yours(self, town: Any) -> None:
        """他人の出品は自分の欄に出ない (正の対照)。"""
        _list_bread(town, _LENA, quantity=1, price=20)

        assert "あなたの出品" not in _state(town, _TOM)


class TestTheBoardIsOnlyShownWhereItStands:
    """板は、そこにあるときだけ見える。"""

    def test_your_own_orders_are_absent_elsewhere(self, town: Any) -> None:
        """板の無い場所では、自分の注文の行も出ない。

        品揃えは常駐しなくなったので、常駐に残るのは自分の注文だけ。それも
        板の前でだけ出る。離れた場所から板の中身が読めると、`market_view` に
        1 手番を払う意味が消える。
        """
        _list_bread(town, _LENA, quantity=1, price=18)
        _walk_away(town, _LENA)

        state = _state(town, _LENA)

        assert "あなたの出品" not in state

    def test_the_absence_is_said_out_loud(self, town: Any) -> None:
        """板の無い場所では、無いことが明示される。

        黙って節を消すと「ここには無い」と「まだ見つけていない」が同じ沈黙に
        潰れ、板を探して手番を溶かす (商人の節で同じ判断をしている)。
        """
        _walk_away(town, _TOM)

        assert "市場の掲示板: (この場所には無い)" in _state(town, _TOM)

    def test_a_world_without_a_market_says_nothing(self, tmp_path: Path) -> None:
        """市場を宣言していない世界では、板の節ごと出ない (正の対照)。

        その世界には板という概念が無く、不在を明示すると既存シナリオの
        prompt が変わって過去 run との比較可能性が切れる。
        """
        runtime = _build(tmp_path, with_market=False)

        assert "市場の掲示板" not in _state(runtime, _TOM)


class TestNothingForSaleIsNotAWallOfNo:
    """買えない品目を並べない。"""

    def test_an_empty_board_shows_no_item_rows(self, town: Any) -> None:
        """出品が 1 つも無ければ、品目の行は出ない。

        「買えない」を毎行並べると、打てない手がプロンプトに毎ターン積み
        上がる。
        """
        state = _board(town, _TOM)

        assert "で買える" not in state

    def test_an_item_with_no_listing_is_left_out(self, town: Any) -> None:
        """出品のある品だけが並ぶ。"""
        _list_bread(town, _LENA, quantity=1, price=18)

        state = _board(town, _TOM)

        assert _BREAD in state
        assert _HERB not in state


class TestTheBuySideAppearsNow:
    """買い注文の列が出る (PR 3)。

    PR 2 では出しませんでした。売る手段 (`market_sell`) が無いのに
    「15G で売れる」と書くと、存在しないツールを本文が宣伝する形になるため。
    ツールが入ったので、ここで初めて出します。
    """

    def _bid(self, runtime: Any, buyer: PlayerId, *, quantity: int, price: int) -> Any:
        return runtime._market_service.place_buy_order(
            buyer, item_label=_HERB, quantity=quantity, unit_price=price,
            current_tick=runtime.current_tick(),
        )

    def test_a_bid_reads_as_something_you_can_sell(self, town: Any) -> None:
        """買い注文のある品は「8G で売れる」と読める。"""
        self._bid(town, _TOM, quantity=2, price=8)

        state = _board(town, _LENA)

        assert "8G で売れる" in state
        assert "買い注文 1件" in state

    def test_the_highest_bid_is_the_one_shown(self, town: Any) -> None:
        """出ている中でいちばん高い値が出る (それが実際に売れる値)。"""
        self._bid(town, _TOM, quantity=1, price=8)
        self._bid(town, _MINA, quantity=1, price=12)

        state = _board(town, _LENA)

        assert "12G で売れる" in state
        assert "8G で売れる" not in state

    def test_your_own_bid_is_not_offered_to_you(self, town: Any) -> None:
        """自分の買い注文は「売れる」に数えない (自分では受けられない)。"""
        self._bid(town, _LENA, quantity=1, price=8)

        assert "8G で売れる" not in _board(town, _LENA)

    def test_a_row_shows_up_when_only_one_side_is_playable(self, town: Any) -> None:
        """片側だけ打てる品目も行を出す。

        「買えない (出品なし) / 8G で売れる」。売る手があるなら、その品目の
        行には意味がある。
        """
        self._bid(town, _TOM, quantity=1, price=8)

        state = _board(town, _LENA)

        assert _HERB in state
        assert "8G で売れる" in state

    def test_a_row_with_nothing_playable_is_left_out(self, town: Any) -> None:
        """両方打てない品目は行ごと出ない (**正の対照**)。"""
        state = _board(town, _LENA)

        assert "で売れる" not in state
        assert "で買える" not in state

    def test_your_own_bid_is_listed_under_its_own_label(self, town: Any) -> None:
        """自分の買い注文は「あなたの買い注文」として別行に出る。

        出品と同じラベルにすると、**自分で自分に売れる**と読める。
        """
        self._bid(town, _LENA, quantity=2, price=8)

        state = _state(town, _LENA)

        assert "あなたの買い注文" in state
        assert "8G" in state

    def test_a_sell_and_a_bid_on_the_same_item_are_two_labelled_rows(
        self, town: Any
    ) -> None:
        """同じ品目に売りと買いを出すと、別ラベルの 2 行が並ぶ。

        engine は交差を潰さないので両方残るが、**自分で自分に売れる**とは
        読めない形になっている必要がある。
        """
        _give(town, _LENA, _HERB, 1)
        town._market_service.place_sell_order(
            _LENA, item_label=_HERB, quantity=1, unit_price=20,
            current_tick=town.current_tick(),
        )
        self._bid(town, _LENA, quantity=1, price=5)

        state = _state(town, _LENA)

        assert "あなたの出品" in state
        assert "あなたの買い注文" in state
