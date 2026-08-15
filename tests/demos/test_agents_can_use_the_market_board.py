"""板を、表示に出ている言葉だけで実際に使える (経済統合 Phase 3)。

**表示 → 引数 → 実行**を実経路で通す。表示に出ている名前をそのまま渡す規約が
守られているかは、resolver と executor を通してみないと分からない。Phase 2 では
ここで resolver の取り違えが捕まった。

もう 1 つ見るのは**表示が正直か**。「18G で買える」と出ている品はその値で買え、
出ていない品を買おうとしたときは、次の一手が分かる形で断られる。表示と実行が
食い違うと、エージェントは板を読んでも行動を決められない。
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Dict, List

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
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
_BREAD = "焼きたてのパン"
_HERB = "薬草"


class _Town:
    """板のある市場町に 2 人を立たせ、市場ツールを実経路で叩く。"""

    def __init__(self, directory: pathlib.Path, *, with_market: bool = True) -> None:
        raw = json.loads(_TOWN.read_text(encoding="utf-8"))
        spawn = raw["players"][0]["spawn_spot"]
        raw["players"].append({
            "id": "tom", "name": "トム", "spawn_spot": spawn,
            "initial_items": [], "initial_gold": 300,
            "persona_prompt": "あなたはトム、この町の荷運び。",
        })
        if with_market:
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

    def exposed_tools(self, player_id: PlayerId = _LENA) -> List[str]:
        capture = _ToolCapture()
        self._state.llm_wiring.llm_client = capture
        self._state.llm_wiring.run_turn(player_id)
        return [tool["function"]["name"] for tool in capture.tools]

    def state_text(self, player_id: PlayerId = _LENA) -> str:
        return self.runtime.build_full_prompt(player_id)["messages"][1]["content"]

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

    def held(self, player_id: PlayerId, label: str) -> int:
        spec_id = self.runtime._item_spec_repo.find_by_name(label).item_spec_id.value
        inventory = self.runtime._player_inventory_repo.find_by_id(player_id)
        counts = count_owned_item_instances_by_spec(inventory, self.runtime._item_repo)
        return sum(c for s, c in counts.items() if s.value == spec_id)

    def gold(self, player_id: PlayerId) -> int:
        return self.runtime._player_status_repo.find_by_id(player_id).gold.value

    def give_gold(self, player_id: PlayerId, amount: int) -> None:
        status = self.runtime._player_status_repo.find_by_id(player_id)
        status.earn_gold(amount)
        self.runtime._player_status_repo.save(status)


class _ToolCapture:
    """いま出ているツール定義を受け取るだけの stub。"""

    def __init__(self) -> None:
        self.tools: List[Any] = []

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        self.tools = tools
        return {"name": "wait", "arguments": {"inner_thought": "x"}}


@pytest.fixture()
def town(tmp_path: pathlib.Path) -> _Town:
    built = _Town(tmp_path)
    # 板で買えるだけの所持金を持たせる。シナリオの初期値は商人の屋台向けで、
    # 板の値付けを試すには足りない。
    built.give_gold(_LENA, 300)
    return built


_MARKET_TOOLS = ("market_list_item", "market_buy", "market_reprice", "market_cancel")


class TestTheMarketToolsAppearOnlyWhereThereIsAMarket:
    """市場ツールは、板を宣言した世界にだけ出る。"""

    def test_they_are_offered_in_a_world_with_a_board(self, town: _Town) -> None:
        """板のある世界では 4 つとも出る。"""
        exposed = town.exposed_tools()

        assert all(name in exposed for name in _MARKET_TOOLS)

    def test_they_are_absent_without_a_market(self, tmp_path: pathlib.Path) -> None:
        """市場を宣言していない世界には 1 つも出ない。

        **正の対照**。宣言の無い世界に並ぶと、対象が永久に空なのに毎ターン
        選択肢へ載る。既存 run のツール一覧も動かさない。
        """
        plain = _Town(tmp_path, with_market=False)

        exposed = plain.exposed_tools()

        assert not any(name in exposed for name in _MARKET_TOOLS)

    def test_they_stay_offered_away_from_the_board(self, town: _Town) -> None:
        """板から離れていてもツールは出たままになる。

        出したり消したりすると、エージェントから見て世界の可能性が揺れる。
        同席は実行時の失敗で伝える。
        """
        _walk_away(town.runtime, _LENA)

        exposed = town.exposed_tools()

        assert all(name in exposed for name in _MARKET_TOOLS)

    def test_using_the_board_from_afar_says_where_to_go(self, town: _Town) -> None:
        """板から離れて使うと、「板のある場所へ」と分かる形で断られる。"""
        town.give(_LENA, _BREAD, 1)
        _walk_away(town.runtime, _LENA)

        result = town.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 18,
            "inner_thought": "出しておこう",
        })

        assert result.success is False
        assert result.error_code == "MARKET_BOARD_NOT_HERE"


class TestTheArgumentsCanBeBuiltFromWhatIsShown:
    """表示に出ている言葉だけで、全ツールの引数が組み立てられる。"""

    def test_you_can_list_an_item_by_its_inventory_name(self, town: _Town) -> None:
        """所持品に出ている名前で出品できる。"""
        town.give(_LENA, _BREAD, 2)
        name = _item_name_in_inventory(town.state_text(), _BREAD)

        result = town.call("market_list_item", {
            "item_label": name, "quantity": 2, "unit_price": 20,
            "inner_thought": "売ってみる",
        })

        assert result.success is True, result.message
        assert town.held(_LENA, _BREAD) == 0

    def test_you_can_buy_by_the_name_on_the_board(self, town: _Town) -> None:
        """掲示板に出ている名前で買える。

        **表示された行から引数を組み立てて実経路へ流す。** 名前が表示と
        食い違っていると、ここで落ちる。
        """
        town.give(_TOM, _BREAD, 1)
        town.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 18,
            "inner_thought": "出す",
        }, player_id=_TOM)
        name, price = _board_row(town.state_text(_LENA))

        result = town.call("market_buy", {
            "item_label": name, "quantity": 1, "inner_thought": "買う",
        })

        assert result.success is True, result.message
        assert town.held(_LENA, _BREAD) == 1
        assert price == 18

    def test_you_can_reprice_by_the_name_in_your_own_row(self, town: _Town) -> None:
        """「あなたの出品」の行に出ている名前で、値を変えられる。"""
        town.give(_LENA, _BREAD, 1)
        town.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 20,
            "inner_thought": "出す",
        })
        name = _own_order_name(town.state_text())

        result = town.call("market_reprice", {
            "item_label": name, "side": "sell", "new_unit_price": 18,
            "inner_thought": "下げる",
        })

        assert result.success is True, result.message
        assert "18G" in result.message

    def test_you_can_cancel_by_the_name_in_your_own_row(self, town: _Town) -> None:
        """同じ名前で取り下げられる。"""
        town.give(_LENA, _BREAD, 1)
        town.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 20,
            "inner_thought": "出す",
        })
        name = _own_order_name(town.state_text())

        result = town.call("market_cancel", {
            "item_label": name, "side": "sell", "inner_thought": "やめる",
        })

        assert result.success is True, result.message
        assert town.held(_LENA, _BREAD) == 1

    def test_no_tool_needs_an_order_number(self, town: _Town) -> None:
        """どのツールも、表示に出ていない識別子を必須にしていない。

        注文 ID を要求すると、表示に出ていない値を渡すことになり、「表示に
        出ている名前をそのまま渡す」規約が崩れる。
        """
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            get_spot_graph_specs,
        )

        for definition, _ in get_spot_graph_specs():
            if definition.name not in _MARKET_TOOLS:
                continue
            required = definition.parameters.get("required", [])
            assert not any("order" in key or "_id" in key for key in required), (
                f"{definition.name} が表示に出ていない識別子を要求している: {required}"
            )


class TestTheBoardTellsTheTruth:
    """表示と実行が食い違わない。"""

    def test_what_it_says_you_can_buy_you_can_buy(self, town: _Town) -> None:
        """「18G で買える」と出ている品は、その値で買える。"""
        town.give(_TOM, _BREAD, 1)
        town.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 18,
            "inner_thought": "出す",
        }, player_id=_TOM)
        before = town.gold(_LENA)

        town.call("market_buy", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "買う",
        })

        assert town.gold(_LENA) == before - 18

    def test_what_it_does_not_show_cannot_be_bought(self, town: _Town) -> None:
        """行に出ていない品を買おうとすると、出ていないと分かる形で断られる。"""
        result = town.call("market_buy", {
            "item_label": _HERB, "quantity": 1, "inner_thought": "買う",
        })

        assert result.success is False
        assert result.error_code == "MARKET_NOTHING_TO_BUY"

    def test_your_own_listing_is_refused_for_its_own_reason(self, town: _Town) -> None:
        """自分の出品しか無い品は、「誰も出していない」とは別の失敗になる。

        次の一手が違う。誰も出していないなら待つしかないが、自分が出している
        なら値を下げる手がある。
        """
        town.give(_LENA, _BREAD, 1)
        town.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 18,
            "inner_thought": "出す",
        })

        result = town.call("market_buy", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "買う",
        })

        assert result.success is False
        assert result.error_code == "MARKET_ONLY_YOUR_OWN"

    def test_buying_more_than_is_shown_says_both_numbers(self, town: _Town) -> None:
        """出ている数より多く買おうとすると、求めた数と買えた数の両方が返る。

        買えた数だけだと、読む側は自分の意図が満たされたか判断できない。
        """
        town.give(_TOM, _BREAD, 2)
        town.call("market_list_item", {
            "item_label": _BREAD, "quantity": 2, "unit_price": 18,
            "inner_thought": "出す",
        }, player_id=_TOM)

        result = town.call("market_buy", {
            "item_label": _BREAD, "quantity": 5, "inner_thought": "たくさん買う",
        })

        assert result.success is True
        assert "5" in result.message and "2" in result.message

    def test_the_breakdown_is_shown_when_prices_differ(self, town: _Town) -> None:
        """値の違う出品にまたがって買うと、内訳が返る。

        平均を出すと、次にいくらで出すかの判断材料が消える。
        """
        town.give(_TOM, _BREAD, 2)
        town.call("market_list_item", {
            "item_label": _BREAD, "quantity": 2, "unit_price": 18,
            "inner_thought": "出す",
        }, player_id=_TOM)
        town.give(_LENA, _BREAD, 1)
        town.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 25,
            "inner_thought": "高く出す",
        })

        result = town.call("market_buy", {
            "item_label": _BREAD, "quantity": 3, "inner_thought": "全部買う",
        }, player_id=_TOM)

        assert result.success is True
        assert "25G" in result.message


def _item_name_in_inventory(state: str, expected: str) -> str:
    """所持品の節から品名を切り出す。"""
    assert expected in state, "所持品に品名が出ていない"
    return expected


def _board_row(state: str) -> tuple:
    """掲示板の行から (品名, 値) を切り出す。"""
    match = re.search(r'"([^"]+)"\s+(\d+)G で買える', state)
    assert match is not None, f"掲示板の行が読めない:\n{state}"
    return match.group(1), int(match.group(2))


def _own_order_name(state: str) -> str:
    """「あなたの出品」の行から品名を切り出す。"""
    match = re.search(r'あなたの出品: "([^"]+)"', state)
    assert match is not None, f"自分の出品の行が読めない:\n{state}"
    return match.group(1)


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


class TestTheBuySideIsUsableFromWhatIsShown:
    """買い板も、表示に出ている言葉だけで使える (PR 3)。"""

    def test_you_can_place_a_bid_by_the_item_name(self, town: _Town) -> None:
        """この世界にある品名で、買い注文を出せる。"""
        result = town.call("market_bid", {
            "item_label": _HERB, "quantity": 2, "unit_price": 7,
            "inner_thought": "薬草がほしい",
        })

        assert result.success is True, result.message
        assert "7G" in result.message

    def test_you_can_sell_by_the_name_on_the_board(self, town: _Town) -> None:
        """「8G で売れる」と出ている品を、その名前で売れる。"""
        town.call("market_bid", {
            "item_label": _HERB, "quantity": 1, "unit_price": 8,
            "inner_thought": "買いたい",
        }, player_id=_TOM)
        town.give(_LENA, _HERB, 1)
        name, price = _sell_side_row(town.state_text(_LENA))

        result = town.call("market_sell", {
            "item_label": name, "quantity": 1, "inner_thought": "売る",
        })

        assert result.success is True, result.message
        assert price == 8

    def test_selling_what_nobody_wants_is_refused(self, town: _Town) -> None:
        """買い注文の無い品を売ろうとすると、出ていないと分かる形で断られる。"""
        town.give(_LENA, _HERB, 1)

        result = town.call("market_sell", {
            "item_label": _HERB, "quantity": 1, "inner_thought": "売る",
        })

        assert result.success is False
        assert result.error_code == "MARKET_NOTHING_TO_SELL"

    def test_selling_into_your_own_bid_is_refused_for_its_own_reason(
        self, town: _Town
    ) -> None:
        """自分の買い注文しか無いときは、別の失敗になる。"""
        town.call("market_bid", {
            "item_label": _HERB, "quantity": 1, "unit_price": 8,
            "inner_thought": "買いたい",
        })
        town.give(_LENA, _HERB, 1)

        result = town.call("market_sell", {
            "item_label": _HERB, "quantity": 1, "inner_thought": "売る",
        })

        assert result.success is False
        assert result.error_code == "MARKET_ONLY_YOUR_OWN_BID"

    def test_selling_more_than_wanted_says_both_numbers(self, town: _Town) -> None:
        """求められている数より多く売ろうとすると、両方の数が返る。"""
        town.call("market_bid", {
            "item_label": _HERB, "quantity": 1, "unit_price": 8,
            "inner_thought": "買いたい",
        }, player_id=_TOM)
        town.give(_LENA, _HERB, 3)

        result = town.call("market_sell", {
            "item_label": _HERB, "quantity": 3, "inner_thought": "まとめて売る",
        })

        assert result.success is True
        assert "3" in result.message and "1" in result.message


def _sell_side_row(state: str) -> tuple:
    """掲示板の行から (品名, 売れる値) を切り出す。

    **行ごとに探す。** 全文へ正規表現をかけると、品名の引用符が行をまたいで
    別の行の数字と組になる (実際に「 6G\n市場の掲示板:\n 」を品名として
    拾った)。表示から引数を作る経路のテストなのに、拾い方を間違えると
    テストの側が嘘になる。
    """
    for line in state.split("\n"):
        match = re.search(r'"([^"]+)"\s+.*?(\d+)G で売れる', line)
        if match is not None:
            return match.group(1), int(match.group(2))
    raise AssertionError(f"買い側の行が読めない:\n{state}")
