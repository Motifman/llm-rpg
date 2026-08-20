"""板の届く範囲はシナリオが宣言する (経済統合 Phase 3)。

**板が場所にあるなら、板を使うことは「その場所に居ること」で、それは「そこに
居る他人と一緒に居ること」**になる。どんな地図を書いても板の前は待ち合わせ場所
になるので、地図では直らない。届く範囲そのものを宣言にする。

人狼系は `at_spot` のままにする — 誰がいつどこに居たかが推理の材料なので、
板の前に立った事実は消せない。MMO 的な世界は `global` にする。**既定は
`at_spot`** で、書かない世界の挙動は変わらない。

**「断られる」試験と「通る」試験は対で置く。** 同席要求を外す変更は、まさに
「〜のとき断られる」を見ている試験を無効化する形になる。`at_spot` 側だけ
書いておくと、既定を `global` にした瞬間に**全部が空振りへ変わって、しかも
通る**。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError
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
_AWAY = "MARKET_BOARD_NOT_HERE"


class _Town:
    """板のある市場町に 2 人を立たせ、届く範囲を変えて実経路で叩く。"""

    def __init__(
        self,
        directory: pathlib.Path,
        *,
        reach: Any = "__unset__",
        with_market: bool = True,
    ) -> None:
        raw = json.loads(_TOWN.read_text(encoding="utf-8"))
        spawn = raw["players"][0]["spawn_spot"]
        raw["players"].append({
            "id": "tom", "name": "トム", "spawn_spot": spawn,
            "initial_items": [], "initial_gold": 300,
            "persona_prompt": "あなたはトム、この町の荷運び。",
        })
        # **「宣言が無い」は自分で作る。** 土台が reach を書き始めたら、
        # 既定を見ているつもりの試験が宣言済みの世界を見はじめる。
        raw.pop("market", None)
        if with_market:
            raw["market"] = {"board_spot": "market_square"}
            if reach != "__unset__":
                raw["market"]["reach"] = reach
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
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            count_owned_item_instances_by_spec,
        )

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

    def exposed_tools(self, player_id: PlayerId = _LENA) -> List[str]:
        capture = _ToolCapture()
        self._state.llm_wiring.llm_client = capture
        self._state.llm_wiring.run_turn(player_id)
        return [tool["function"]["name"] for tool in capture.tools]


class _ToolCapture:
    def __init__(self) -> None:
        self.tools: List[Any] = []

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        self.tools = tools
        return {"name": "wait", "arguments": {"inner_thought": "x"}}


def _board_spot_name(runtime: Any) -> str:
    graph = runtime._spot_graph_repo.find_graph()
    return graph.get_spot(runtime._market_service.board_spot_id).name


def _line_containing(text: str, needle: str) -> str:
    """その語を含む行だけを返す。

    **全文へ `in` をかけない。** 板のある場所は行き先の一覧にも名前が出るので、
    全文だと「板の在り処が書かれている」と「隣の spot として名前がある」が
    区別できず、何もしなくても通る。
    """
    for line in text.splitlines():
        if needle in line:
            return line
    raise AssertionError(f"{needle!r} を含む行が無い:\n{text}")


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


def _list_from_afar(town: _Town, player_id: PlayerId, price: int = 18):
    town.give(player_id, _BREAD, 1)
    _walk_away(town.runtime, player_id)
    return town.call("market_list_item", {
        "item_label": _BREAD, "quantity": 1, "unit_price": price,
        "inner_thought": "出す",
    }, player_id=player_id)


@pytest.fixture()
def near(tmp_path: pathlib.Path) -> _Town:
    """届く範囲を宣言していない世界 (既定)。"""
    built = _Town(tmp_path)
    built.give_gold(_LENA, 300)
    return built


@pytest.fixture()
def far(tmp_path: pathlib.Path) -> _Town:
    """どこからでも届く世界。"""
    built = _Town(tmp_path, reach="global")
    built.give_gold(_LENA, 300)
    return built


class TestTheReachIsDeclaredByTheScenario:
    """届く範囲は宣言で決まり、書かなければ場所に縛られる。"""

    def test_a_world_that_says_nothing_stays_tied_to_the_place(
        self, near: _Town
    ) -> None:
        """`reach` を書かない世界は、板の前でしか使えないままになる。

        既定を変えると、既存シナリオの挙動が黙って変わる。
        """
        assert _list_from_afar(near, _LENA).error_code == _AWAY

    def test_at_spot_can_be_said_out_loud(self, tmp_path: pathlib.Path) -> None:
        """`"at_spot"` と明示的に書ける (既定と同じ挙動になる)。"""
        town = _Town(tmp_path, reach="at_spot")

        assert _list_from_afar(town, _LENA).error_code == _AWAY

    def test_global_can_be_said_out_loud(self, far: _Town) -> None:
        """`"global"` と書くと、板から離れていても使える。"""
        assert _list_from_afar(far, _LENA).success is True

    def test_a_reach_the_world_does_not_have_is_refused_at_startup(
        self, tmp_path: pathlib.Path
    ) -> None:
        """知らない届く範囲を書くと、起動時に落ちる。

        黙って既定へ倒すと、`"nearby"` と書いた作者は場所に縛られたままの
        世界を「どこからでも届く」と思い込む。
        """
        with pytest.raises(ScenarioLoadError) as caught:
            _Town(tmp_path, reach="nearby")

        assert "nearby" in str(caught.value)
        assert "at_spot" in str(caught.value)
        assert "global" in str(caught.value)

    def test_a_world_without_a_market_has_no_board_either_way(
        self, tmp_path: pathlib.Path
    ) -> None:
        """市場を宣言していない世界には、届く範囲に関係なく板が無い。"""
        plain = _Town(tmp_path, with_market=False)

        assert "market_view" not in plain.exposed_tools()


class TestWhatIsRefusedNearAndAllowedFar:
    """6 つの経路すべてを、断られる側と通る側で対にして見る。

    片側だけ書くと、既定が変わった瞬間に**全部が空振りへ変わって、しかも
    通る**。
    """

    def _bid(self, town: _Town, player_id: PlayerId, price: int = 12):
        return town.call("market_bid", {
            "item_label": _BREAD, "quantity": 1, "unit_price": price,
            "inner_thought": "買いたい",
        }, player_id=player_id)

    def test_listing_is_refused_from_afar(self, near: _Town) -> None:
        """離れた場所からは出品できない。"""
        assert _list_from_afar(near, _LENA).error_code == _AWAY

    def test_listing_works_from_afar_when_it_reaches(self, far: _Town) -> None:
        """届く世界では、離れた場所から出品できる。品は板へ預けられる。"""
        result = _list_from_afar(far, _LENA)

        assert result.success is True, result.message
        assert far.held(_LENA, _BREAD) == 0

    def test_buying_is_refused_from_afar(self, near: _Town) -> None:
        """離れた場所からは買えない。"""
        near.give(_TOM, _BREAD, 1)
        near.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 18,
            "inner_thought": "出す",
        }, player_id=_TOM)
        _walk_away(near.runtime, _LENA)

        result = near.call("market_buy", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "買う",
        })

        assert result.error_code == _AWAY

    def test_buying_works_from_afar_when_it_reaches(self, far: _Town) -> None:
        """届く世界では、離れた場所から買える。品と gold がその場で動く。"""
        far.give(_TOM, _BREAD, 1)
        far.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 18,
            "inner_thought": "出す",
        }, player_id=_TOM)
        _walk_away(far.runtime, _LENA)
        before = far.gold(_LENA)

        result = far.call("market_buy", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "買う",
        })

        assert result.success is True, result.message
        assert far.held(_LENA, _BREAD) == 1
        assert far.gold(_LENA) == before - 18

    def test_bidding_is_refused_from_afar(self, near: _Town) -> None:
        """離れた場所からは買い注文を出せない。"""
        _walk_away(near.runtime, _LENA)

        assert self._bid(near, _LENA).error_code == _AWAY

    def test_bidding_works_from_afar_when_it_reaches(self, far: _Town) -> None:
        """届く世界では、離れた場所から買い注文を出せる。"""
        _walk_away(far.runtime, _LENA)

        assert self._bid(far, _LENA).success is True

    def test_selling_is_refused_from_afar(self, near: _Town) -> None:
        """離れた場所からは買い注文を受けられない。"""
        near.give_gold(_TOM, 300)
        self._bid(near, _TOM)
        near.give(_LENA, _BREAD, 1)
        _walk_away(near.runtime, _LENA)

        result = near.call("market_sell", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "売る",
        })

        assert result.error_code == _AWAY

    def test_selling_works_from_afar_when_it_reaches(self, far: _Town) -> None:
        """届く世界では、離れた場所から買い注文を受けて売れる。"""
        far.give_gold(_TOM, 300)
        self._bid(far, _TOM)
        far.give(_LENA, _BREAD, 1)
        _walk_away(far.runtime, _LENA)
        before = far.gold(_LENA)

        result = far.call("market_sell", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "売る",
        })

        assert result.success is True, result.message
        assert far.gold(_LENA) == before + 12

    def test_repricing_is_refused_from_afar(self, near: _Town) -> None:
        """離れた場所からは値を変えられない。"""
        near.give(_LENA, _BREAD, 1)
        near.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 20,
            "inner_thought": "出す",
        })
        _walk_away(near.runtime, _LENA)

        result = near.call("market_reprice", {
            "item_label": _BREAD, "side": "sell", "new_unit_price": 18,
            "inner_thought": "下げる",
        })

        assert result.error_code == _AWAY

    def test_repricing_works_from_afar_when_it_reaches(self, far: _Town) -> None:
        """届く世界では、離れた場所から値を変えられる。"""
        far.give(_LENA, _BREAD, 1)
        far.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 20,
            "inner_thought": "出す",
        })
        _walk_away(far.runtime, _LENA)

        result = far.call("market_reprice", {
            "item_label": _BREAD, "side": "sell", "new_unit_price": 18,
            "inner_thought": "下げる",
        })

        assert result.success is True, result.message

    def test_cancelling_is_refused_from_afar(self, near: _Town) -> None:
        """離れた場所からは取り下げられない。"""
        near.give(_LENA, _BREAD, 1)
        near.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 20,
            "inner_thought": "出す",
        })
        _walk_away(near.runtime, _LENA)

        result = near.call("market_cancel", {
            "item_label": _BREAD, "side": "sell", "inner_thought": "やめる",
        })

        assert result.error_code == _AWAY

    def test_cancelling_works_from_afar_when_it_reaches(self, far: _Town) -> None:
        """届く世界では、離れた場所から取り下げて品を取り戻せる。"""
        far.give(_LENA, _BREAD, 1)
        far.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 20,
            "inner_thought": "出す",
        })
        _walk_away(far.runtime, _LENA)

        result = far.call("market_cancel", {
            "item_label": _BREAD, "side": "sell", "inner_thought": "やめる",
        })

        assert result.success is True, result.message
        assert far.held(_LENA, _BREAD) == 1

    def test_reading_is_refused_from_afar(self, near: _Town) -> None:
        """離れた場所からは板を読めない。"""
        _walk_away(near.runtime, _LENA)

        result = near.call("market_view", {"inner_thought": "見たい"})

        assert result.error_code == _AWAY

    def test_reading_works_from_afar_when_it_reaches(self, far: _Town) -> None:
        """届く世界では、離れた場所から板を読める。"""
        far.give(_TOM, _BREAD, 1)
        far.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 18,
            "inner_thought": "出す",
        }, player_id=_TOM)
        _walk_away(far.runtime, _LENA)

        result = far.call("market_view", {"inner_thought": "見たい"})

        assert result.success is True, result.message
        assert "18G で買える" in result.message


class TestThePromptSaysHowFarItReachesAndWhereItStands:
    """届く範囲と、板が物としてどこに在るかは別の事実で、両方要る。"""

    def test_a_place_bound_board_says_here_or_not_here(self, near: _Town) -> None:
        """場所に縛られた板は、ここにあるか無いかで書かれる。"""
        assert "ここにある" in near.state_text(_LENA)

        _walk_away(near.runtime, _LENA)

        assert "この場所には無い" in near.state_text(_LENA)

    def test_a_board_that_reaches_says_so_from_anywhere(self, far: _Town) -> None:
        """どこからでも届く板は、離れていてもそう書かれる。"""
        _walk_away(far.runtime, _LENA)

        assert "どこからでも" in far.state_text(_LENA)
        assert "この場所には無い" not in far.state_text(_LENA)

    def test_it_still_says_where_the_board_stands(self, far: _Town) -> None:
        """届く世界でも、板が在る場所の名前は出る。

        **受け取れなかった品は板の足元に置かれる。** それは自分が居ない場所
        なので、取りに行くには名前が要る。届く範囲は使い方の話で、板がどこに
        在るかは物の在り処の話。別の事実なので、片方で片方を消さない。
        """
        _walk_away(far.runtime, _LENA)

        line = _line_containing(far.state_text(_LENA), "市場の掲示板")

        assert _board_spot_name(far.runtime) in line

    def test_your_own_orders_follow_you_when_the_board_reaches(
        self, far: _Town
    ) -> None:
        """届く世界では、自分の注文が離れた場所でも常駐に出る。

        「預けた品がどこからも見えない」を避けるのが理由なので、届く範囲が
        広がれば常駐も広がる。
        """
        far.give(_LENA, _BREAD, 1)
        far.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 20,
            "inner_thought": "出す",
        })
        _walk_away(far.runtime, _LENA)

        assert "あなたの出品" in far.state_text(_LENA)

    def test_your_own_orders_stay_at_the_board_when_it_does_not_reach(
        self, near: _Town
    ) -> None:
        """場所に縛られた世界では、離れると自分の注文も出ない (**正の対照**)。"""
        near.give(_LENA, _BREAD, 1)
        near.call("market_list_item", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 20,
            "inner_thought": "出す",
        })
        _walk_away(near.runtime, _LENA)

        assert "あなたの出品" not in near.state_text(_LENA)


class TestGoodsYouCannotHoldSayWhereTheyWereLeft:
    """受け取れなかった品の置き場所は、名前で伝える。

    届く世界では、買い手が**一度も行っていない場所**に品が置かれる。
    「受け取れませんでした」だけだと、品が消えたと読むか、板の前まで行って
    初めて気づくことになる。
    """

    def test_the_notice_names_the_place(self, far: _Town) -> None:
        """持ちきれずに板の足元へ置かれたことが、場所の名前つきで届く。"""
        far.give_gold(_LENA, 300)
        far.call("market_bid", {
            "item_label": _BREAD, "quantity": 1, "unit_price": 12,
            "inner_thought": "買いたい",
        })
        inventory = far.runtime._player_inventory_repo.find_by_id(_LENA)
        while not inventory.is_inventory_full():
            far.give(_LENA, _BREAD, 1)
            inventory = far.runtime._player_inventory_repo.find_by_id(_LENA)
        far.give(_TOM, _BREAD, 1)
        _walk_away(far.runtime, _TOM)
        far.call("market_sell", {
            "item_label": _BREAD, "quantity": 1, "inner_thought": "売る",
        }, player_id=_TOM)

        line = _line_containing(far.state_text(_LENA), "足元に置かれた")

        assert _board_spot_name(far.runtime) in line
