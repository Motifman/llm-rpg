"""板は引かないと見えない (経済統合 Phase 3)。

板をプロンプトに常駐させると、**見るのが無料**になる。無料で最新の板が見える
世界では、値を読む巧拙が消える。引くのに 1 手番かかるなら、見た値は次の手番
には古い — **情報の鮮度が資源になる**。この世界に足したいのはその性質で、
`market_view` はそのための入口。

同時に、これは安く測れる kill test でもある。板がまだ場所に縛られているうちに
1 run 回せば、「**板を見るために 1 手番払うか**」だけを単独で測れる。ここで
払わないなら、板をどこからでも引けるようにしても板は使われない。

常駐から外すのは**他人の値**だけ。自分が板に預けた品は常駐に残す。外すと
預けた品がどこからも見えなくなり、値を変える・取り下げる手がかりが消える。
期限切れの通知を 1 回見落とした時点で取り戻せなくなる (静かな失敗)。
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
_MINA = PlayerId(3)
_BREAD = "焼きたてのパン"
_HERB = "薬草"
_VIEW = "market_view"


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
        # 板の厚みを見るには**同じ品を出す人が 2 人**要る。同じ人は同じ品の
        # 売り注文を 2 件出せない (値を変えるなら値の付け直しを使う)。
        raw["players"].append({
            "id": "mina", "name": "ミナ", "spawn_spot": spawn,
            "initial_items": [], "initial_gold": 300,
            "persona_prompt": "あなたはミナ、この町の粉屋。",
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

    def view(self, player_id: PlayerId = _LENA) -> str:
        result = self.call(_VIEW, {"inner_thought": "板を見る"}, player_id=player_id)
        assert result.success is True, result.message
        return result.message

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

    def give_gold(self, player_id: PlayerId, amount: int) -> None:
        status = self.runtime._player_status_repo.find_by_id(player_id)
        status.earn_gold(amount)
        self.runtime._player_status_repo.save(status)

    def list_item(
        self, player_id: PlayerId, label: str, price: int, quantity: int = 1
    ) -> None:
        self.give(player_id, label, quantity)
        result = self.call("market_list_item", {
            "item_label": label, "quantity": quantity, "unit_price": price,
            "inner_thought": "出す",
        }, player_id=player_id)
        assert result.success is True, result.message

    def bid(
        self, player_id: PlayerId, label: str, price: int, quantity: int = 1
    ) -> None:
        result = self.call("market_bid", {
            "item_label": label, "quantity": quantity, "unit_price": price,
            "inner_thought": "買いたい",
        }, player_id=player_id)
        assert result.success is True, result.message


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


class TestWhatOneLookAtTheBoardTellsYou:
    """1 回引けば、値を付けるのに要るものが揃っている。"""

    def test_it_shows_the_best_price_on_each_side_and_how_deep_it_is(
        self, town: _Town
    ) -> None:
        """買える単価・売れる単価・それぞれの件数が、品目ごとに 1 行で出る。"""
        town.list_item(_TOM, _BREAD, 18)
        town.list_item(_MINA, _BREAD, 22)
        town.bid(_TOM, _BREAD, 15)

        shown = town.view()

        assert "18G で買える" in shown
        assert "出品 2件" in shown
        assert "15G で売れる" in shown
        assert "買い注文 1件" in shown

    def test_it_shows_what_the_item_last_actually_sold_for(self, town: _Town) -> None:
        """直近に成立した単価が出る。**望まれた値ではなく成立した値**。

        最良の売り値・買い値は「誰かが望んでいる値」でしかない。実際に成立した
        値が、値を付けるときの唯一の確かな手がかりになる。
        """
        town.list_item(_TOM, _BREAD, 18)
        town.call("market_buy", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "買う",
        })

        shown = town.view()

        assert "18G" in shown
        assert "成立" in shown

    def test_an_item_that_never_traded_shows_no_settled_price(
        self, town: _Town
    ) -> None:
        """一度も約定していない品目に、成立した値の欄は出ない。

        0G と書くと「0G で成立した」と読める。**無いことは無いと言う。**
        """
        town.list_item(_TOM, _BREAD, 18)

        shown = town.view()

        assert "0G" not in shown
        assert "成立" not in shown

    def test_your_own_orders_do_not_count_as_the_going_rate(
        self, town: _Town
    ) -> None:
        """自分の注文は需給の集約に数えない。自分では受けられないため。"""
        town.list_item(_LENA, _BREAD, 18)

        shown = town.view()

        assert "18G で買える" not in shown

    def test_your_own_orders_are_still_named_when_nothing_else_is_there(
        self, town: _Town
    ) -> None:
        """自分の出品しか無くても、「他に無い」と「自分は出している」が両方分かる。

        集約から外すだけだと「いま出ているものは無い」としか出ず、預けた品が
        **消えた**と読める。
        """
        town.list_item(_LENA, _BREAD, 18)

        shown = town.view()

        assert "出ているものは無い" in shown
        assert "あなたの出品" in shown
        assert _BREAD in shown

    def test_an_order_awaiting_collection_is_hidden_from_others(
        self, town: _Town
    ) -> None:
        """引き取り待ちの注文は、他人が引いた板には出ない。誰にも買えないため。"""
        town.list_item(_TOM, _BREAD, 18)
        order = town.runtime._market_service.board().orders[0]
        town.runtime._market_service._store.save(
            town.runtime._market_service.board().awaiting_collection(order.order_id)
        )

        shown = town.view()

        assert "18G で買える" not in shown

    def test_an_empty_board_says_so(self, town: _Town) -> None:
        """板に何も出ていないとき、そう分かる文面が返る。

        黙って空を返すと「引けなかった」と区別がつかない。
        """
        shown = town.view()

        assert "出ているものは無い" in shown


class TestTheBoardIsOnlyReadableWhereItStands:
    """板は物として置かれているので、その場所でだけ引ける。"""

    def test_reading_it_from_afar_says_where_to_go(self, town: _Town) -> None:
        """離れた場所で引くと、板のある場所へ行けと分かる形で断られる。"""
        _walk_away(town.runtime, _LENA)

        result = town.call(_VIEW, {"inner_thought": "見たい"})

        assert result.success is False
        assert result.error_code == "MARKET_BOARD_NOT_HERE"

    def test_it_is_offered_in_a_world_with_a_board(self, town: _Town) -> None:
        """板のある世界では market_view が出る。"""
        assert _VIEW in town.exposed_tools()

    def test_it_is_absent_without_a_market(self, tmp_path: pathlib.Path) -> None:
        """市場を宣言していない世界には market_view が出ない。"""
        plain = _Town(tmp_path, with_market=False)

        assert _VIEW not in plain.exposed_tools()


class TestTheBoardIsNoLongerFreeToSee:
    """他人の値はプロンプトに常駐しない。見るには引く。"""

    def test_other_peoples_prices_are_not_in_the_prompt(self, town: _Town) -> None:
        """板の前に立っていても、他人の出品の値段はプロンプトに出ない。"""
        town.list_item(_TOM, _BREAD, 18)

        assert "18G で買える" not in town.state_text(_LENA)

    def test_your_own_orders_stay_in_the_prompt(self, town: _Town) -> None:
        """自分の出品はプロンプトに出続ける。

        外すと預けた品がどこからも見えなくなり、値を変える・取り下げる手が
        かりが消える。
        """
        town.list_item(_LENA, _BREAD, 18)

        state = town.state_text(_LENA)

        assert "あなたの出品" in state
        assert _BREAD in state

    def test_the_prompt_still_says_where_the_board_is(self, town: _Town) -> None:
        """板がここにあるかどうかは、引かなくても分かる。

        在り処を伝えないと、板を探して手番が溶ける。
        """
        assert "掲示板" in town.state_text(_LENA)

        _walk_away(town.runtime, _LENA)

        assert "この場所には無い" in town.state_text(_LENA)


class TestWhatYouReadIsStillThereNextTurn:
    """引いた値は、次の手番のプロンプトに残っている。"""

    def test_the_board_you_read_survives_into_the_next_prompt(
        self, town: _Town
    ) -> None:
        """引いた内容が本人の直近の出来事に残る。

        **これが無いと払った手番に意味が無い。** 引くのに 1 手番、出品にもう
        1 手番かかるので、引いた結果が次の手番で消えていると、どれだけ賢い
        エージェントでも板の値を使って値付けできない。
        """
        town.list_item(_TOM, _BREAD, 18)

        town.view(_LENA)

        assert "18G で買える" in town.state_text(_LENA)


class TestReadingTheBoardIsNotAnEventForAnyoneElse:
    """板を引いても、それは誰の観測にもならない。

    情報を得る行為に配信を付けると、大量のエージェントが居る世界で観測が洪水に
    なる。板の前で誰かが読んでいるのが見えないのは現実と違うが、**言いたければ
    その場で言える**ので、可視性の道は残っている。
    """

    def test_listing_an_item_is_visible_to_someone_standing_there(
        self, town: _Town
    ) -> None:
        """**正の対照**。板に出すのは同席者から見える。"""
        town.list_item(_LENA, _BREAD, 18)

        assert "レナ" in town.state_text(_TOM)

    def test_reading_the_board_is_not(self, town: _Town) -> None:
        """板を引いたことは、同席者のプロンプトに出ない。"""
        town.list_item(_TOM, _BREAD, 18)
        before = town.state_text(_TOM)

        town.view(_LENA)

        assert "レナ" not in town.state_text(_TOM).replace(before, "")
