"""職の分かれた町で、交換しなければ誰も食べていけないか。

このシナリオは**エージェント同士の交渉**を観察するためのもので、世界の側に
「交換しないと詰む」構造が実在することが前提になる。前提が崩れたまま実 LLM
run を回すと、「交渉が起きなかった」と「交渉しなくても済む世界だった」を
区別できない。ここでは行動を stub で固定し、世界の側だけを確かめる。

見るのは 3 つ。

1. **誰も 1 人では食べられない** — 職能が本当に閉じているか
2. **交換すれば全員が食べられる** — 閉じすぎて詰んでいないか
3. **初手が存在する** — 三者それぞれに、他人の同意を待たずに打てる 1 手があるか

3 が最も落としやすい。焼き手が最初のパンを焼くまで、空腹の解決手段はこの世界
に存在しない。その最初の 1 斤に他人の同意が要ると、run の冒頭で全員が
相手待ちになって何も始まらない。市場町 v1 では薬草の再生宣言漏れを同じ形の
テストで捕まえている。
"""

from __future__ import annotations

import pathlib
import shutil
from typing import Any, Dict, List

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_SCENARIO = (
    pathlib.Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "market_town_v2_trade.json"
)
_BREAD = "焼きたてのパン"
_HERB = "薬草"
_WHEAT = "麦束"

#: 摘み手 / 焼き手 / 麦刈り。シナリオの players 順に 1, 2, 3。
_LENA = PlayerId(1)
_TOM = PlayerId(2)
_MINA = PlayerId(3)


class _Town:
    """職の分かれた町を 1 つ立ち上げ、ツールを実経路で叩けるようにする。"""

    def __init__(self, directory: pathlib.Path) -> None:
        shutil.copy(_SCENARIO, directory / _SCENARIO.name)
        manager = GameRuntimeManager(
            scenarios_dir=directory, characters_path=directory / "characters.json",
        )
        character = manager.create_character(CharacterCreateRequest(name="レナ"))
        summary = manager.create_session(
            SessionCreateRequest(
                world_id="market_town_v2_trade", character_ids=[character.id]
            )
        )
        self._state = manager._sessions[summary.session_id]

    @property
    def runtime(self) -> Any:
        return self._state.runtime

    def call(self, tool: str, args: Dict[str, Any], who: PlayerId):
        self._state.llm_wiring.llm_client = StubLlmClient(
            tool_call_to_return={"name": tool, "arguments": args},
        )
        return self._state.llm_wiring.run_turn(who)

    def go(self, who: PlayerId, place: str):
        return self.call(
            "travel_to", {"destination_label": place, "inner_thought": "向かう"}, who,
        )

    def do(self, who: PlayerId, target: str, action: str):
        return self.call(
            "interact",
            {"target_label": target, "action_name": action, "inner_thought": "やる"},
            who,
        )

    def let_time_pass(self, ticks: int) -> None:
        """世界の時間だけを進める (その間の手番では何もさせない)。"""
        self._state.llm_wiring.llm_client = StubLlmClient(
            tool_call_to_return={"name": "wait", "arguments": {"inner_thought": "待つ"}},
        )
        for _ in range(ticks):
            self.runtime._simulation_service.tick()

    def gold(self, who: PlayerId) -> int:
        return self.runtime._player_status_repo.find_by_id(who).gold.value

    def has(self, who: PlayerId, name: str) -> int:
        inventory = self.runtime._player_inventory_repo.find_by_id(who)
        wanted = next(
            definition.spec_id.value
            for definition in self.runtime.scenario.item_spec_definitions
            if definition.name == name
        )
        return sum(
            1
            for _, item_instance_id in inventory.iter_occupied_slots()
            if self.runtime._item_repo.find_by_id(item_instance_id)
            .item_spec.item_spec_id.value
            == wanted
        )

    def tool_names_for(self, who: PlayerId) -> List[str]:
        capture = _ToolCapture()
        self._state.llm_wiring.llm_client = capture
        self._state.llm_wiring.run_turn(who)
        return [tool["function"]["name"] for tool in capture.tools]


class _ToolCapture:
    def __init__(self) -> None:
        self.tools: List[Any] = []

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        self.tools = tools
        return {"name": "wait", "arguments": {"inner_thought": "x"}}


@pytest.fixture()
def town(tmp_path: pathlib.Path) -> _Town:
    return _Town(tmp_path)


class TestNobodyCanFeedThemselvesAlone:
    """職能は本当に閉じている (1 人で食べ物にたどり着けない)。"""

    def test_the_gatherer_cannot_bake(self, town: _Town) -> None:
        """摘み手は窯へ行っても、麦束が無いので焼けない。

        「焼けない」のが麦不足であって職能の壁ではないことを、失敗文で確かめる。
        麦さえあれば誰でも焼ける世界にしてある — 壁は**麦の入手経路**の側。
        """
        town.go(_LENA, "かまど小屋")
        town.let_time_pass(3)

        result = town.do(_LENA, "石窯", "bake_bread")

        assert result.success is False
        assert "麦束がない" in result.message

    def test_the_reaper_cannot_turn_wheat_into_food(self, town: _Town) -> None:
        """麦刈りは麦を刈れるが、麦は食べられず商人も買い取らない。"""
        town.go(_MINA, "井戸端")
        town.let_time_pass(3)
        town.go(_MINA, "麦畑")
        town.let_time_pass(2)
        reaped = town.do(_MINA, "麦の畝", "reap_wheat")

        eaten = town.call("use_item", {"item_label": _WHEAT, "inner_thought": "食う"}, _MINA)

        assert reaped.success is True
        assert town.has(_MINA, _WHEAT) == 1
        assert eaten.success is False

    def test_the_merchant_does_not_sell_food(self, town: _Town) -> None:
        """商人はパンを売らない。金があっても商人からは食べ物を買えない。

        ここが開いていると「困ったら商人」で交渉が回避され、シナリオの目的が
        丸ごと空振りする。
        """
        result = town.call(
            "buy_item", {"item_label": _BREAD, "quantity": 1, "inner_thought": "買う"}, _LENA,
        )

        assert result.success is False

    def test_the_merchant_does_not_buy_wheat(self, town: _Town) -> None:
        """商人は麦を買い取らない。麦刈りは金を作れず、物々交換しか道がない。

        買い取ってしまうと、麦刈りも「売って買う」で 1 人で閉じてしまい、
        gold を挟まない取引が run に現れない。
        """
        town.go(_MINA, "井戸端")
        town.let_time_pass(3)
        town.go(_MINA, "麦畑")
        town.let_time_pass(2)
        town.do(_MINA, "麦の畝", "reap_wheat")
        town.go(_MINA, "井戸端")
        town.let_time_pass(2)
        town.go(_MINA, "市場の広場")
        town.let_time_pass(3)

        result = town.call(
            "sell_item", {"item_label": _WHEAT, "quantity": 1, "inner_thought": "売る"}, _MINA,
        )

        assert result.success is False
        assert town.gold(_MINA) == 0


class TestTradingLetsEveryoneEat:
    """交換すれば、三人とも食べ物にたどり着ける。"""

    def test_wheat_for_bread_feeds_the_reaper(self, town: _Town) -> None:
        """麦刈りは、刈った麦をパンと交換して食べられる (gold を挟まない取引)。"""
        _reap_and_return(town, _MINA)
        _bake_and_return(town, _TOM)

        offered = town.call(
            "trade_offer",
            {
                "target_player_label": "トム",
                "gives": {"items": [{"item_label": _WHEAT, "quantity": 1}]},
                "asks": {"items": [{"item_label": _BREAD, "quantity": 1}]},
                "inner_thought": "麦とパンを換えたい",
            },
            _MINA,
        )
        accepted = town.call("trade_accept", {"inner_thought": "受ける"}, _TOM)
        eaten = town.call("use_item", {"item_label": _BREAD, "inner_thought": "食べる"}, _MINA)

        assert offered.success is True
        assert accepted.success is True
        assert eaten.success is True
        assert town.has(_TOM, _WHEAT) == 1, "焼き手が次の 1 斤の材料を得ている"

    def test_gold_for_bread_feeds_the_gatherer(self, town: _Town) -> None:
        """摘み手は、薬草を売った金でパンを買える (gold を挟む取引)。"""
        _gather_and_return(town, _LENA)
        sold = town.call(
            "sell_item", {"item_label": _HERB, "quantity": 1, "inner_thought": "売る"}, _LENA,
        )
        _bake_and_return(town, _TOM)

        offered = town.call(
            "trade_offer",
            {
                "target_player_label": "レナ",
                "gives": {"items": [{"item_label": _BREAD, "quantity": 1}]},
                "asks": {"gold": 8},
                "inner_thought": "パンを売りたい",
            },
            _TOM,
        )
        accepted = town.call("trade_accept", {"inner_thought": "受ける"}, _LENA)
        eaten = town.call("use_item", {"item_label": _BREAD, "inner_thought": "食べる"}, _LENA)

        assert sold.success is True
        assert offered.success is True
        assert accepted.success is True
        assert eaten.success is True
        # 12G + 売って 6G = 18G、パンに 8G 払って 10G。
        assert town.gold(_LENA) == 10
        assert town.gold(_TOM) == 8

    def test_the_baker_eats_what_he_bakes(self, town: _Town) -> None:
        """焼き手は自分で焼いて食べられる (誰の同意も要らない)。"""
        _bake_and_return(town, _TOM)

        eaten = town.call("use_item", {"item_label": _BREAD, "inner_thought": "食べる"}, _TOM)

        assert eaten.success is True


class TestEveryoneHasAFirstMove:
    """三者それぞれに、他人の同意を待たずに打てる最初の 1 手がある。

    ここが無いと run の冒頭で全員が相手待ちになり、交渉が始まる前に世界が
    止まる。「交渉が起きなかった」の原因がシナリオ側になってしまう。
    """

    def test_the_baker_can_bake_without_asking_anyone(self, town: _Town) -> None:
        """焼き手は最初の 1 斤を、誰にも頼らずに焼ける。

        最初の麦束を初期所持で渡してある。ここを空にすると、世界で最初の
        パンが「麦刈りとの取引成立」を待つことになり、冒頭が相手待ちで固まる。
        """
        assert town.has(_TOM, _WHEAT) == 1

        town.go(_TOM, "かまど小屋")
        town.let_time_pass(3)
        baked = town.do(_TOM, "石窯", "bake_bread")

        assert baked.success is True
        assert town.has(_TOM, _BREAD) == 1

    def test_the_gatherer_can_earn_without_asking_anyone(self, town: _Town) -> None:
        """摘み手は、誰にも頼らずに薬草を摘んで金に換えられる。"""
        _gather_and_return(town, _LENA)

        sold = town.call(
            "sell_item", {"item_label": _HERB, "quantity": 1, "inner_thought": "売る"}, _LENA,
        )

        assert sold.success is True
        assert town.gold(_LENA) == 18

    def test_the_reaper_can_produce_without_asking_anyone(self, town: _Town) -> None:
        """麦刈りは、誰にも頼らずに麦束を手に入れられる。"""
        _reap_and_return(town, _MINA)

        assert town.has(_MINA, _WHEAT) == 1

    def test_the_first_bread_does_not_need_a_trade(self, town: _Town) -> None:
        """世界で最初のパンは、取引が 1 件も成立しなくても焼き上がる。

        3 人の初手を全部踏んでも、取引は 1 件も要らない。**その状態で世界に
        食べ物が存在する**ことが、冒頭のデッドロックが無いことの定義。
        """
        _bake_and_return(town, _TOM)
        _gather_and_return(town, _LENA)
        _reap_and_return(town, _MINA)

        assert town.runtime._pending_trade_offer_store.list_all() == ()
        assert town.has(_TOM, _BREAD) == 1


class TestTheSourcesRefillThemselves:
    """薬草と麦が、刈った後にまた実る。

    再生の宣言 (reactive_bindings) を書き忘れても**世界は問題なく起動する**。
    起動するので、実 run を最後まで回して初めて「1 回しか採れなかった」と
    分かる。市場町 v1 では薬草の再生宣言漏れをこの形のテストで捕まえた。
    麦は職能が閉じている分だけ影響が重く、止まると焼き手ごと詰む。
    """

    def test_the_herb_grows_back(self, town: _Town) -> None:
        """摘んだ薬草は、しばらく経てばまた摘める。"""
        town.go(_LENA, "薬草の土手")
        town.let_time_pass(3)
        town.do(_LENA, "薬草の茂み", "gather_herb")

        too_soon = town.do(_LENA, "薬草の茂み", "gather_herb")
        town.let_time_pass(10)
        after_waiting = town.do(_LENA, "薬草の茂み", "gather_herb")

        assert too_soon.success is False, "摘んだ直後にまた摘めてしまう"
        assert after_waiting.success is True, "待っても薬草が戻らない"

    def test_the_wheat_grows_back(self, town: _Town) -> None:
        """刈った麦は、しばらく経てばまた刈れる。

        戻らないと麦束が世界に 1 つしか存在せず、パンも 2 つ目が焼けない。
        全員が飢えて run が「交渉の観察」にならない。
        """
        town.go(_MINA, "井戸端")
        town.let_time_pass(3)
        town.go(_MINA, "麦畑")
        town.let_time_pass(2)
        town.do(_MINA, "麦の畝", "reap_wheat")

        too_soon = town.do(_MINA, "麦の畝", "reap_wheat")
        town.let_time_pass(12)
        after_waiting = town.do(_MINA, "麦の畝", "reap_wheat")

        assert too_soon.success is False, "刈った直後にまた刈れてしまう"
        assert after_waiting.success is True, "待っても麦が戻らない"


class TestTheNightHasSomethingToDoBesidesWaiting:
    """夜に「休む」を選べる (待つ以外の表現手段がある)。

    市場町 v1 では、深夜に「もう休む頃合いか」と判断したのに wait しか手段が
    無く、3 連発で loop_guard が発火した。停滞と生活の区別がつかなくなるので、
    横になる手を世界の側に置いた。
    """

    def test_resting_is_available_where_everyone_meets(self, town: _Town) -> None:
        """全員が集まる広場で、横になって休める。"""
        result = town.do(_LENA, "宿の軒先", "rest")

        assert result.success is True
        assert "横になって" in result.message or "眠" in result.message


class TestTheWorldOffersOnlyWhatItHas:
    """出ているツールが、この世界の実態と合っている。"""

    def test_the_trade_tools_are_offered(self, town: _Town) -> None:
        """人同士の取引ツールが 3 つとも出ている (宣言が効いている)。"""
        names = town.tool_names_for(_LENA)

        assert {"trade_offer", "trade_accept", "trade_decline"} <= set(names)

    @pytest.mark.parametrize("absent", ["give_item", "attack", "tend_to_player"])
    def test_disabled_tools_are_not_offered(self, town: _Town, absent: str) -> None:
        """落としたツールは出ない。

        `give_item` を落としているのは意図的。無償で渡せると条件つきの取引を
        通らずに済み、Phase 2 で検証したい経路が空振りする。市場町 v1 でも
        落としてあるので、baseline との比較も保てる。
        """
        assert absent not in town.tool_names_for(_LENA)


def _gather_and_return(town: _Town, who: PlayerId) -> None:
    """土手で薬草を 1 つ摘んで広場へ戻る。"""
    town.go(who, "薬草の土手")
    town.let_time_pass(3)
    town.do(who, "薬草の茂み", "gather_herb")
    town.go(who, "市場の広場")
    town.let_time_pass(3)


def _reap_and_return(town: _Town, who: PlayerId) -> None:
    """麦畑で麦を 1 束刈って広場へ戻る。"""
    town.go(who, "井戸端")
    town.let_time_pass(3)
    town.go(who, "麦畑")
    town.let_time_pass(2)
    town.do(who, "麦の畝", "reap_wheat")
    town.go(who, "井戸端")
    town.let_time_pass(2)
    town.go(who, "市場の広場")
    town.let_time_pass(3)


def _bake_and_return(town: _Town, who: PlayerId) -> None:
    """かまど小屋でパンを 1 つ焼いて広場へ戻る。"""
    town.go(who, "かまど小屋")
    town.let_time_pass(3)
    town.do(who, "石窯", "bake_bread")
    town.go(who, "市場の広場")
    town.let_time_pass(3)
