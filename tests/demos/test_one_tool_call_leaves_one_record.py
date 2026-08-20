"""ツールを 1 回呼んだら、行動記録は 1 件だけできる。

`wait` は長らく 2 件作っていた。`WorldRuntime.do_wait` が自分で記録し、
executor が返した結果 DTO を**ターン実行が他の全ツールと同じように**もう
1 件記録していたため。

見た目の重複だけではない。行動記録はエピソード記憶の入力なので、同じ決定が
2 度流れる。「あのとき 2 回待った」という、起きていない過去が残る。

**その世界に出ている全ツールを総当たり**する。失敗した呼び出しも 1 件記録
されるので、引数を用意できないツールも同じ検査にかけられる。新しいツールを
足した人がこの規約を知らなくても、記録経路を 2 本にした瞬間に落ちる。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
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

#: 引数なしで成功まで届くツール。ここは「成功した呼び出しも 1 件」を見る。
_NO_ARG_CALLS: Dict[str, Dict[str, Any]] = {
    "wait": {"reason": "様子を見る", "inner_thought": "待とう"},
    "explore": {"inner_thought": "見て回る"},
    "listen": {"inner_thought": "耳を澄ます"},
}


@pytest.fixture()
def town(tmp_path: pathlib.Path) -> Any:
    raw = json.loads(_TOWN.read_text(encoding="utf-8"))
    (tmp_path / "market_town_v1.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8",
    )
    manager = GameRuntimeManager(
        scenarios_dir=tmp_path, characters_path=tmp_path / "characters.json",
    )
    character = manager.create_character(CharacterCreateRequest(name="レナ"))
    summary = manager.create_session(
        SessionCreateRequest(world_id="market_town_v1", character_ids=[character.id])
    )
    return manager._sessions[summary.session_id]


def _call(state: Any, tool: str, args: Dict[str, Any]) -> Any:
    state.llm_wiring.llm_client = StubLlmClient(
        tool_call_to_return={"name": tool, "arguments": args},
    )
    return state.llm_wiring.run_turn(_LENA)


def _records(state: Any) -> List[Any]:
    return list(state.runtime._action_result_store.get_recent(_LENA, 50))


def _count_for(state: Any, tool: str) -> int:
    return sum(1 for entry in _records(state) if entry.tool_name == tool)


class _ToolCapture:
    """いま出ているツール定義を受け取るだけの stub。"""

    def __init__(self) -> None:
        self.tools: List[Any] = []

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        self.tools = tools
        return {"name": "wait", "arguments": {"inner_thought": "x"}}


def _exposed_tool_names(state: Any) -> List[str]:
    capture = _ToolCapture()
    state.llm_wiring.llm_client = capture
    state.llm_wiring.run_turn(_LENA)
    return [tool["function"]["name"] for tool in capture.tools]


class TestEachToolCallIsRecordedExactlyOnce:
    """1 回の呼び出しにつき、行動記録はちょうど 1 件。"""

    @pytest.mark.parametrize("tool", sorted(_NO_ARG_CALLS))
    def test_a_single_call_leaves_a_single_record(self, town: Any, tool: str) -> None:
        """ツールを 1 回呼ぶと、そのツール名の記録がちょうど 1 件できる。"""
        result = _call(town, tool, _NO_ARG_CALLS[tool])

        assert result.success is True, f"{tool} が失敗している: {result.message}"
        mine = [entry for entry in _records(town) if entry.tool_name == tool]
        assert len(mine) == 1, (
            f"{tool} の記録が {len(mine)} 件ある。記録経路が 2 本になっていないか "
            f"({[e.action_summary for e in mine]})"
        )

    def test_waiting_twice_leaves_exactly_two_records(self, town: Any) -> None:
        """2 回待てば 2 件。1 件に潰れてもいけない (正の対照)。

        「1 件だけ」を数えるテストは、記録が 1 件も増えなくなっても緑になる。
        呼んだ回数と記録の件数が一致することまで見る。
        """
        _call(town, "wait", _NO_ARG_CALLS["wait"])
        _call(town, "wait", _NO_ARG_CALLS["wait"])

        waits = [entry for entry in _records(town) if entry.tool_name == "wait"]

        assert len(waits) == 2

    def test_the_record_keeps_the_reason_in_its_result(self, town: Any) -> None:
        """残る 1 件は、待った理由を結果の文面に持っている。

        重複を消すときに、理由の載っている方を落とすと情報が減る。
        """
        _call(town, "wait", _NO_ARG_CALLS["wait"])

        entry = next(e for e in _records(town) if e.tool_name == "wait")

        assert "様子を見る" in entry.result_summary


class TestEveryExposedToolIsRecordedOnce:
    """その世界に出ている全ツールを総当たりして、記録が 2 件にならないことを見る。

    引数を用意しないので多くは失敗するが、**失敗も 1 件記録される**ので
    「1 回の呼び出し = 1 件」の検査としては同じ。ここが総当たりなので、
    新しいツールを足せば自動で対象になる。
    """

    def test_no_tool_records_itself_twice(self, town: Any) -> None:
        """どのツールも、1 回の呼び出しで 2 件以上は記録しない。"""
        exposed = _exposed_tool_names(town)
        assert len(exposed) > 10, f"ツールが出ていない (総当たりが空振り): {exposed}"

        duplicated = {}
        for tool in exposed:
            before = _count_for(town, tool)
            _call(town, tool, {"inner_thought": "試す"})
            added = _count_for(town, tool) - before
            if added > 1:
                duplicated[tool] = added

        assert duplicated == {}, f"1 回の呼び出しで 2 件以上記録したツール: {duplicated}"
