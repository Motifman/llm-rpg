"""市場町で「摘む → 売る → 買う → 食べる」が 1 人で 1 周するか。

このシナリオは経済ループの発見をエージェントに観察するためのもので、**世界の
側にループが実在すること**が前提になる。前提が崩れたまま実 LLM run を回すと、
「エージェントがループを見つけられなかった」と「世界にループが無かった」を
区別できない。ここでは行動を stub で固定し、世界の側だけを確かめる。
"""

from __future__ import annotations

import pathlib
import shutil
from typing import Any, Dict

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import GameRuntimeManager
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

_SCENARIO = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "scenarios" / "market_town_v1.json"
)
_BREAD = "焼きたてのパン"
_HERB = "薬草"


class _Town:
    """市場町を 1 つ立ち上げ、ツールを実経路で叩けるようにする。"""

    def __init__(self, directory: pathlib.Path) -> None:
        shutil.copy(_SCENARIO, directory / _SCENARIO.name)
        manager = GameRuntimeManager(
            scenarios_dir=directory, characters_path=directory / "characters.json",
        )
        character = manager.create_character(CharacterCreateRequest(name="レナ"))
        summary = manager.create_session(
            SessionCreateRequest(world_id="market_town_v1", character_ids=[character.id])
        )
        self._state = manager._sessions[summary.session_id]
        self.player_id = PlayerId(int(self.runtime.scenario.player_spawns[0].player_id))

    @property
    def runtime(self) -> Any:
        return self._state.runtime

    def call(self, tool: str, args: Dict[str, Any]):
        self._state.llm_wiring.llm_client = StubLlmClient(
            tool_call_to_return={"name": tool, "arguments": args},
        )
        return self._state.llm_wiring.run_turn(self.player_id)

    def let_time_pass(self, ticks: int) -> None:
        """世界の時間だけを進める。

        **その間の手番では何もさせない。** tick の中で手番が回ることがあり、
        stub は直前の道具呼び出しを返し続けるので、放っておくと「待っている
        間に勝手にもう一度摘む」ことになる。実際それで薬草の再生を測り
        損ねた (再生した瞬間に自動で摘まれ、いつまでも available=False に
        見えていた)。
        """
        self._state.llm_wiring.llm_client = StubLlmClient(
            tool_call_to_return={"name": "wait", "arguments": {"inner_thought": "待つ"}},
        )
        for _ in range(ticks):
            self.runtime._simulation_service.tick()

    @property
    def gold(self) -> int:
        return self.runtime._player_status_repo.find_by_id(self.player_id).gold.value


@pytest.fixture()
def town(tmp_path: pathlib.Path) -> _Town:
    return _Town(tmp_path)


class TestTheLoopExistsInTheWorld:
    """摘む → 売る → 買う → 食べる が実際につながっている。"""

    def test_one_full_loop_feeds_the_agent(self, town: _Town) -> None:
        """薬草を摘んで売り、その金でパンを買って食べるまでが 1 周する。"""
        town.call("travel_to", {"destination_label": "薬草の土手", "inner_thought": "摘みに行く"})
        town.let_time_pass(3)
        gathered = town.call(
            "interact",
            {"target_label": "薬草の茂み", "action_name": "gather_herb", "inner_thought": "摘む"},
        )
        town.call("travel_to", {"destination_label": "市場の広場", "inner_thought": "売りに行く"})
        town.let_time_pass(3)
        sold = town.call("sell_item", {"item_label": _HERB, "quantity": 1, "inner_thought": "売る"})
        bought = town.call("buy_item", {"item_label": _BREAD, "quantity": 1, "inner_thought": "買う"})
        eaten = town.call("use_item", {"item_label": _BREAD, "inner_thought": "食べる"})

        assert gathered.success is True
        assert sold.success is True
        assert bought.success is True
        assert eaten.success is True
        # 12G → 売って 18G → 買って 8G。差し引き 4G 減るのが 1 周の収支で、
        # 「働けば暮らせるが、1 周では貯まらない」テンポになっている。
        assert town.gold == 8

    def test_the_loop_fits_in_the_planned_tick_budget(self, town: _Town) -> None:
        """1 周が 10 tick 以内で終わる (40 tick の run で 2〜3 周観察できる)。"""
        town.call("travel_to", {"destination_label": "薬草の土手", "inner_thought": "摘みに行く"})
        town.let_time_pass(3)
        town.call(
            "interact",
            {"target_label": "薬草の茂み", "action_name": "gather_herb", "inner_thought": "摘む"},
        )
        town.call("travel_to", {"destination_label": "市場の広場", "inner_thought": "戻る"})
        town.let_time_pass(3)
        town.call("sell_item", {"item_label": _HERB, "quantity": 1, "inner_thought": "売る"})
        town.call("buy_item", {"item_label": _BREAD, "quantity": 1, "inner_thought": "買う"})
        town.call("use_item", {"item_label": _BREAD, "inner_thought": "食べる"})

        assert town.runtime.current_tick() <= 10


class TestTheWorldKeepsTheAgentWorking:
    """初手で買えるが、稼がないと続かない。"""

    def test_the_first_bread_is_affordable_but_the_second_is_not(self, town: _Town) -> None:
        """初期所持金ではパンを 1 つ買えて、2 つ目は買えない。

        0G から始めると、売りを見つけられなかった run で買いが一度も実行されず、
        「ツールが使えない」と「ループを発見できない」を切り分けられなくなる。
        """
        first = town.call("buy_item", {"item_label": _BREAD, "quantity": 1, "inner_thought": "買う"})
        second = town.call("buy_item", {"item_label": _BREAD, "quantity": 1, "inner_thought": "もう 1 つ"})

        assert first.success is True
        assert second.success is False
        assert second.error_code == "BUY_ITEM_NOT_ENOUGH_GOLD"

    def test_the_herb_patch_needs_time_before_the_next_harvest(self, town: _Town) -> None:
        """摘んだ直後は摘めず、時間を置くとまた摘める (無限に稼げない)。"""
        town.call("travel_to", {"destination_label": "薬草の土手", "inner_thought": "摘みに行く"})
        town.let_time_pass(3)
        town.call(
            "interact",
            {"target_label": "薬草の茂み", "action_name": "gather_herb", "inner_thought": "摘む"},
        )

        immediately = town.call(
            "interact",
            {"target_label": "薬草の茂み", "action_name": "gather_herb", "inner_thought": "もう一度"},
        )
        # 再生は最後の収穫から 6 tick。ここでは判定が入る tick を跨げるよう
        # 余裕を持って進める (境界そのものの検査はシナリオの責務ではない)。
        town.let_time_pass(10)
        later = town.call(
            "interact",
            {"target_label": "薬草の茂み", "action_name": "gather_herb", "inner_thought": "また摘む"},
        )

        assert immediately.success is False
        assert later.success is True


class TestTheWorldOffersOnlyWhatItHas:
    """この世界に無い手段は並ばない。"""

    def test_the_economy_tools_are_offered(self, town: _Town) -> None:
        """商人が居るので、買いと売りの両方が使える。"""
        names = [
            definition.name
            for definition in town.runtime.get_tool_definitions(for_every_player=True)
        ]

        assert "buy_item" in names
        assert "sell_item" in names

    @pytest.mark.parametrize("absent", ["attack", "tend_to_player", "give_item"])
    def test_tools_without_targets_are_not_offered(self, town: _Town, absent: str) -> None:
        """対象が構造として永久に居ないツールは出さない。

        モンスターの居ない世界の attack と同じ判断。1 人の世界では give_item の
        相手も、tend_to_player の対象も、この先ずっと現れない。
        """
        names = [
            definition.name
            for definition in town.runtime.get_tool_definitions(for_every_player=True)
        ]

        assert absent not in names
