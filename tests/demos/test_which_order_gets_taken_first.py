"""突き合わせの順番と、それが何に乗っているか (経済統合 Phase 3)。

**価格優先 → 時間優先。** 決めずに書くと engine が黙って選び、値の時系列に
「なぜその注文が先に消えたか」の根拠が無くなる。

そして時間優先は、`order_id` が板の中で単調に増えることに乗っている。**その
依存はどこにも書かれていなかった** — UUID に変えた人は、自分が突き合わせの
規則を変えたことに気づけない。単調性そのものを見る試験を 1 件置いて、黙って
壊れる状態を終わらせる。

板を引けば第三者も同じ値に届くことも、ここで見る。板の動きは誰にも配信されなく
なったが、**押しつけられないだけで公開されている。**
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_TOWN = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
)
_LENA = PlayerId(1)
_TOM = PlayerId(2)
#: 板の前に立っているだけの人。**誰の相手でもない。**
_MINA = PlayerId(3)
_BREAD = "焼きたてのパン"


class _Town:
    """板のある市場町に 3 人を立たせる。3 人目は誰の取引にも関わらない。"""

    def __init__(self, directory: pathlib.Path) -> None:
        raw = json.loads(_TOWN.read_text(encoding="utf-8"))
        spawn = raw["players"][0]["spawn_spot"]
        for pid, name in (("tom", "トム"), ("mina", "ミナ")):
            raw["players"].append({
                "id": pid, "name": name, "spawn_spot": spawn,
                "initial_items": [], "initial_gold": 300,
                "persona_prompt": f"あなたは{name}。",
            })
        raw["market"] = {"board_spot": "market_square"}
        (directory / "market_town_v1.json").write_text(
            json.dumps(raw, ensure_ascii=False), encoding="utf-8",
        )
        manager = GameRuntimeManager(
            scenarios_dir=directory, characters_path=directory / "characters.json",
        )
        character = manager.create_character(CharacterCreateRequest(name="レナ"))
        summary = manager.create_session(
            SessionCreateRequest(world_id="market_town_v1", character_ids=[character.id])
        )
        self._state = manager._sessions[summary.session_id]

    @property
    def runtime(self) -> Any:
        return self._state.runtime

    def call(self, tool: str, args: Dict[str, Any], player_id: PlayerId = _LENA):
        self._state.llm_wiring.llm_client = StubLlmClient(
            tool_call_to_return={"name": tool, "arguments": args},
        )
        return self._state.llm_wiring.run_turn(player_id)

    def state_text(self, player_id: PlayerId) -> str:
        return self.runtime.build_full_prompt(player_id)["messages"][1]["content"]

    def recent(self, player_id: PlayerId) -> str:
        """その人の「直近の出来事」だけを返す。

        **全文を見ない。** 品名も人名もプロンプトの他の節に出るので、全文だと
        「届いた」と「そこに居るのが見えている」が区別できない。
        """
        text = self.state_text(player_id)
        head = "【直近の出来事】"
        if head not in text:
            return ""
        return text.split(head, 1)[1].split("【", 1)[0]

    def give(self, player_id: PlayerId, label: str, count: int = 1) -> None:
        spec_id = self.runtime._item_spec_repo.find_by_name(label).item_spec_id.value
        grant_item_specs_to_inventory(
            player_id,
            tuple(ItemSpecId.create(spec_id) for _ in range(count)),
            self.runtime._item_repo,
            self.runtime._item_spec_repo,
            self.runtime._player_inventory_repo,
            overflow_sink=IGNORE_OVERFLOW,
        )

    def give_gold(self, player_id: PlayerId, amount: int) -> None:
        status = self.runtime._player_status_repo.find_by_id(player_id)
        status.earn_gold(amount)
        self.runtime._player_status_repo.save(status)

    def list_item(self, player_id: PlayerId, price: int, quantity: int = 1) -> None:
        self.give(player_id, _BREAD, quantity)
        result = self.call("market_list_item", {
            "item_label": _BREAD, "quantity": quantity, "unit_price": price,
            "inner_thought": "出す",
        }, player_id=player_id)
        assert result.success is True, result.message


@pytest.fixture()
def town(tmp_path: pathlib.Path) -> _Town:
    built = _Town(tmp_path)
    built.give_gold(_LENA, 300)
    return built


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


class TestTheBoardItselfCarriesTheVisibility:
    """押しつけられないが、公開されている。"""

    def test_a_third_party_can_still_read_the_same_prices(self, town: _Town) -> None:
        """届かなかった値も、板を引けば第三者が読める。

        **可視性を捨てたのではなく、押しつけをやめた。** 引く手番を払えば、
        誰でも同じ値と直近の約定価格に届く。
        """
        town.list_item(_TOM, 18)

        result = town.call("market_view", {"inner_thought": "見る"}, player_id=_MINA)

        assert result.success is True, result.message
        assert "18G で買える" in result.message


class TestWhichOrderGetsTakenFirst:
    """突き合わせは価格優先、同じ値なら先に出した方から。"""

    def _sell_side(self, town: _Town) -> Any:
        return town.runtime._market_service

    def test_the_cheaper_listing_is_taken_first(self, town: _Town) -> None:
        """安い出品から約定する。"""
        town.list_item(_TOM, 22)
        town.list_item(_MINA, 18)

        result = town.call("market_buy", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "買う",
        })

        assert result.success is True, result.message
        assert self._sell_side(town).board().last_trade_price_of(
            town.runtime._item_spec_repo.find_by_name(_BREAD).item_spec_id.value
        ) == 18

    def test_the_older_listing_wins_at_the_same_price(self, town: _Town) -> None:
        """同じ値の出品が 2 件並ぶと、先に出した方から約定する。

        決めずに書くと engine が黙って選び、**値の時系列に「誰の注文が先に
        消えたか」の根拠が無くなる**。
        """
        town.list_item(_TOM, 18)
        town.list_item(_MINA, 18)
        first = town.runtime._market_service.board().orders[0]

        town.call("market_buy", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "買う",
        })

        remaining = town.runtime._market_service.board().orders
        assert all(o.order_id != first.order_id for o in remaining)

    def test_the_higher_bid_is_taken_first(self, town: _Town) -> None:
        """買い注文は高い方から受けられる。"""
        town.give_gold(_TOM, 300)
        town.give_gold(_MINA, 300)
        for who, price in ((_TOM, 8), (_MINA, 12)):
            town.call("market_bid", {
                "item_label": _BREAD, "quantity": 1, "unit_price": price,
                "inner_thought": "買いたい",
            }, player_id=who)
        town.give(_LENA, _BREAD, 1)
        before = town.runtime._player_status_repo.find_by_id(_LENA).gold.value

        town.call("market_sell", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "売る",
        })

        after = town.runtime._player_status_repo.find_by_id(_LENA).gold.value
        assert after - before == 12

    def test_the_older_bid_wins_at_the_same_price(self, town: _Town) -> None:
        """同じ値の買い注文が 2 件並ぶと、先に出した方が受けられる。"""
        town.give_gold(_TOM, 300)
        town.give_gold(_MINA, 300)
        for who in (_TOM, _MINA):
            town.call("market_bid", {
                "item_label": _BREAD, "quantity": 1, "unit_price": 12,
                "inner_thought": "買いたい",
            }, player_id=who)
        first = town.runtime._market_service.board().orders[0]
        town.give(_LENA, _BREAD, 1)

        town.call("market_sell", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "売る",
        })

        remaining = town.runtime._market_service.board().orders
        assert all(o.order_id != first.order_id for o in remaining)

    def test_changing_your_price_does_not_send_you_to_the_back(
        self, town: _Town
    ) -> None:
        """値を変えても順番は変わらない。

        **値を動かす人を後ろへ回さない。** この世界で見たいのは値が動くこと
        なので、動かした人が損をする規則は目的と逆を向く。「下げたのに順番で
        負けて売れない」は、値を下げても報われないという読みを作る。

        代償はある。**先に雑な値で並んでおいて、あとから直す**のが有利になる。
        いまは見たいものと一致しているので採るが、板が厚くなったら見直す点。
        """
        town.list_item(_TOM, 22)
        town.list_item(_MINA, 20)
        older = town.runtime._market_service.board().orders[0]
        town.call("market_reprice", {
            "item_label": _BREAD, "side": "sell", "new_unit_price": 20,
            "inner_thought": "揃える",
        }, player_id=_TOM)

        town.call("market_buy", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "買う",
        })

        remaining = town.runtime._market_service.board().orders
        assert all(o.order_id != older.order_id for o in remaining)

    def test_a_purchase_across_two_listings_follows_the_same_order(
        self, town: _Town
    ) -> None:
        """複数の注文にまたがって買うときも、安い方から順に取る。"""
        town.list_item(_TOM, 22)
        town.list_item(_MINA, 18)

        result = town.call("market_buy", {
            "item_label": _BREAD, "quantity": 2, "inner_thought": "まとめて買う",
        })

        assert result.success is True, result.message
        assert "18" in result.message and "22" in result.message


class TestTimePriorityRidesOnTheOrderIds:
    """先に出した方が先、は order_id が単調に増えることに乗っている。"""

    def test_the_ids_only_ever_increase(self, town: _Town) -> None:
        """板に置かれた順に、order_id は必ず増える。

        **突き合わせの「同じ値なら先に出した方」は、この単調性に乗っている**
        (並べ替えの鍵が `order_id`)。ここを変えるなら、突き合わせの規則を
        変えることになる。UUID や払い出しの変更は、この試験が落ちて初めて
        「規則を変えた」と分かる — 書かれていないと黙って壊れる。
        """
        town.list_item(_TOM, 18)
        town.list_item(_MINA, 20)
        town.give_gold(_TOM, 300)
        town.call("market_bid", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 8,
            "inner_thought": "買いたい",
        }, player_id=_TOM)

        ids = [o.order_id.value for o in town.runtime._market_service.board().orders]

        assert len(ids) >= 3
        assert ids == sorted(ids)
        assert len(set(ids)) == len(ids)
