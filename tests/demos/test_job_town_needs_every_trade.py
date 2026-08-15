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

from tests.support.overflow_sinks import IGNORE_OVERFLOW

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

    #: 市場の広場からの道順。``travel_to`` は隣接 spot しか受け付けない。
    _ROUTES = {
        "薬草の土手": ("薬草の土手",),
        "井戸端": ("井戸端",),
        "かまど小屋": ("かまど小屋",),
        "麦畑": ("井戸端", "麦畑"),
    }

    def travel(self, who: PlayerId, place: str) -> None:
        """広場から目的地まで、隣接を辿って移動する。"""
        for leg in self._ROUTES[place]:
            self.go(who, leg)
            self.let_time_pass(3)

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


#: 設計表そのもの。**行 = 人、列 = 仕事、値 = できるか。**
#:
#: v2.0 ではこの表を PR 本文に書いておきながら、シナリオに実装せず、
#: テストでも 1 マスしか見ていなかった。しかもその 1 マスは「麦が無いから
#: 焼けない」を見ていて、**表と逆の意味**を固定していた。実 run では麦刈りが
#: 自分で焼いて自分で食べ、三者の相互依存が丸ごと崩れた。
#:
#: 教訓は「設計表を書いたら、テストは表に対して書く」。実装の現状に対して
#: 書くと、実装が表とずれていても緑になる。
_JOB_MATRIX = {
    #        摘む   刈る   焼く
    "レナ":  (True, False, False),
    "トム":  (False, False, True),
    "ミナ":  (False, True, False),
}

#: 仕事 → (場所, 対象, action_name, その仕事に要る資源)
_WORK = (
    ("摘む", "薬草の土手", "薬草の茂み", "gather_herb", None),
    ("刈る", "麦畑", "麦の畝", "reap_wheat", None),
    ("焼く", "かまど小屋", "石窯", "bake_bread", _WHEAT),
)

_WHO = {"レナ": _LENA, "トム": _TOM, "ミナ": _MINA}


class TestOnlyItsOwnerCanDoEachJob:
    """職 × 行為の総当たり。表の 9 マスを 1 マスずつ確かめる。

    資源不足で落ちるのを「職能の壁」と読み違えないよう、**その仕事に要る
    資源は先に持たせてから**試す。焼きだけが麦束を要するので、焼きの行は
    3 人とも麦束を持った状態で叩く。
    """

    @pytest.mark.parametrize("person", sorted(_JOB_MATRIX))
    @pytest.mark.parametrize("job", [w[0] for w in _WORK])
    def test_each_cell_of_the_matrix(self, town: _Town, person: str, job: str) -> None:
        """表のとおり、その仕事ができるのは担当者だけになる。"""
        place, target, action, needs = next(w[1:] for w in _WORK if w[0] == job)
        who = _WHO[person]
        expected = _JOB_MATRIX[person][[w[0] for w in _WORK].index(job)]

        if needs:
            _give(town, who, needs)
        town.travel(who, place)

        result = town.do(who, target, action)

        assert result.success is expected, (
            f"{person} が「{job}」を "
            f"{'できない' if expected else 'できてしまう'}: {result.message}"
        )

    @pytest.mark.parametrize("person", ["レナ", "ミナ"])
    def test_the_refusal_names_the_trade_not_the_resource(
        self, town: _Town, person: str
    ) -> None:
        """断り文は「材料が無い」ではなく「自分の仕事ではない」と伝える。

        資源不足の文面で断ると、材料さえ集めればできると読める。**集めても
        できない**ことが伝わらないと、他人と交換する理由に辿り着けない。
        """
        who = _WHO[person]
        _give(town, who, _WHEAT)
        town.go(who, "かまど小屋")
        town.let_time_pass(4)

        result = town.do(who, "石窯", "bake_bread")

        assert result.success is False
        assert "あの人だけ" in result.message
        assert "麦束がない" not in result.message


class TestNobodyCanFeedThemselvesAlone:
    """職能は本当に閉じている (1 人で食べ物にたどり着けない)。"""

    def test_the_gatherer_cannot_bake_even_holding_wheat(self, town: _Town) -> None:
        """摘み手は麦束を持っていても焼けない。壁は資源ではなく職能。

        **v2.0 ではここが「麦が無いから焼けない」だった。**麦さえ手に入れば
        誰でも焼ける世界になっていて、実 run では麦刈りが自分で焼いて自分で
        食べ、三者の相互依存が丸ごと崩れた。資源を持たせた状態で試す。
        """
        _give(town, _LENA, _WHEAT)
        town.go(_LENA, "かまど小屋")
        town.let_time_pass(3)

        result = town.do(_LENA, "石窯", "bake_bread")

        assert result.success is False
        assert "パンを焼けるのはあの人だけ" in result.message

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
        # 麦 1 束からパンが 2 つ焼ける。1 つだと焼いた人が食べて終わりで、
        # 売り物が世界に一度も存在しない (v2.0 の実 run で実際に起きた)。
        assert town.has(_TOM, _BREAD) == 2

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
        assert town.has(_TOM, _BREAD) == 2


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


class TestTheOfferWindowOutlastsTheErrand:
    """提案の期限が、相手が現物を用意して戻るまでの往復より長い。

    承諾には相手が現物を持っている必要があるので、**予約注文 (gold を出して
    パンを求める) は往復より期限が短いと構造的に必ず流れる**。v2.0 の実 run
    がまさにそれで、生産の往復 12 手番に対して期限は既定の 10 手番だった。
    摘み手は 4 回「金は払う、幾らだ」と言葉で交渉したのに、一度も成立して
    いない。

    期限そのものの値を書くのではなく、**実際に歩かせて測った往復と比べる**。
    値を書くだけだと、地図を広げたときに気付けない。
    """

    #: 実測の往復に対して求める余裕。
    #:
    #: ここで測れるのは**機械的な最短往復**で、実 run はこれより必ず遅い。
    #: 手番は 3 人で分け合うので 1 人が続けて動けず、道具を選ぶ前に考える
    #: 間も空く。v2.0 の実 run では 1 人あたり 1 行動に平均 2.5 手番かかって
    #: いた (98 行動 / 3 人 / 80 手番)。最短往復の 2 倍を下限にする。
    _MARGIN = 2

    def test_the_declared_window_covers_a_bread_errand_with_margin(
        self, town: _Town
    ) -> None:
        """広場で受けた注文を、焼いて持ち帰るまでの往復の 2 倍以上を期限にする。

        期限の値を直接書かない。**実際に歩かせて測った往復と比べる**ので、
        地図を広げたり道を切ったりしたときに、期限が足りなくなったことが
        ここで分かる。
        """
        declared = town.runtime.scenario.player_trade_offer_expires_in_ticks
        assert declared is not None, "期限を宣言していない (engine の既定に倒れている)"

        started = town.runtime.current_tick()
        _bake_and_return(town, _TOM)
        errand = town.runtime.current_tick() - started

        assert declared >= errand * self._MARGIN, (
            f"最短往復 {errand} 手番に対して期限 {declared} 手番。"
            f"実 run はこれより遅いので {errand * self._MARGIN} 手番は要る"
        )


class TestTheProductionLoopDoesNotDetourThroughTheSquare:
    """麦畑とかまど小屋が直接つながっている。

    `travel_to` は隣接 spot しか受け付けない。v2.0 では かまど小屋 が広場から
    の行き止まりで、畑からは 3 ホップだった。実 run では焼き手 (t50) と
    麦刈り (t58) が「かまど小屋」への移動に実際に失敗している。往復が長い
    ことは、提案の期限が足りなくなる原因でもある。
    """

    def test_the_field_and_the_bake_house_are_neighbours(self, town: _Town) -> None:
        """麦畑から、広場を経由せずにかまど小屋へ行ける。"""
        town.travel(_MINA, "麦畑")

        moved = town.go(_MINA, "かまど小屋")

        assert moved.success is True, moved.message


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

    @pytest.mark.parametrize("absent", ["attack", "tend_to_player"])
    def test_disabled_tools_are_not_offered(self, town: _Town, absent: str) -> None:
        """落としたツールは出ない。"""
        assert absent not in town.tool_names_for(_LENA)

    def test_giving_is_offered_alongside_trading(self, town: _Town) -> None:
        """無償で渡す手も出ている。条件つきの取引と両方が選べる。

        v2.0 では「無償で渡せると条件つきの取引を通らずに済む」と考えて
        落としていた。実 run で分かったのは逆で、**贈与はこの世界で自然に
        起きる取引の形**だった (焼き手は「焼いてやる」と言い、摘み手は
        「金は払う」と言う。どちらも本人の性格から出ている)。

        落としたままだと、渡したい側は地面に置いて相手に拾わせるしかない。
        置き逃げになり、第三者に拾われる危険まで負う。**やりたいことに対して
        正規の手段が無い**状態は、世界の質感として正しくない。

        どちらを選ぶかはエージェントの判断で、その判断自体が観測対象になる。
        """
        names = town.tool_names_for(_LENA)

        assert "give_item" in names
        assert "trade_offer" in names


def _give(town: _Town, who: PlayerId, item_name: str) -> None:
    """テストの都合で持ち物を足す (職能の壁を、資源不足と切り分けるため)。"""
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        grant_item_specs_to_inventory,
    )
    from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

    spec_id = next(
        definition.spec_id.value
        for definition in town.runtime.scenario.item_spec_definitions
        if definition.name == item_name
    )
    grant_item_specs_to_inventory(
        who,
        (ItemSpecId.create(spec_id),),
        town.runtime._item_repo,
        town.runtime._item_spec_repo,
        town.runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


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
