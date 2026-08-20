"""シナリオが宣言した経済が、実際にエージェントのプロンプトへ届くか。

商人と初期所持金は宣言できるようになった (PR #1144) が、宣言が本番経路に
届いていなければ「シナリオに書いたのに効かない」静かな失敗になる。ここでは
1 本の世界を実際に組み立て、商人の品揃えと所持金がプロンプトに出ること、
宣言していない世界の文面が一切変わらないことを確かめる。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI = PlayerId(1)


class _PromptCaptureClient:
    """LLM を呼ばずに、組み立てられたプロンプトだけを受け取る stub。"""

    def __init__(self) -> None:
        self.messages: list = []
        self.tools: list = []

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        self.messages = messages
        self.tools = tools
        return {"name": "wait", "arguments": {}}


def _prompt_of(runtime, player_id: PlayerId) -> str:
    client = _PromptCaptureClient()
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
    )
    wiring.run_phase_a(player_id)
    return client.messages[-1]["content"]


def _drill_raw() -> Dict[str, Any]:
    return json.loads(_DRILL.read_text(encoding="utf-8"))


def _write(tmp_path: Path, raw: Dict[str, Any], name: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def _world_with_a_merchant_beside(raw: Dict[str, Any], player_index: int = 0) -> Dict[str, Any]:
    """先頭プレイヤーと同じ spot に商人を置き、所持金を宣言した世界を返す。"""
    player = raw["players"][player_index]
    item_spec = raw["item_specs"][0]["id"]
    raw["merchants"] = [
        {
            "id": "gustav",
            "name": "商人グスタフ",
            "spot": player["spawn_spot"],
            "sells": [{"item_spec": item_spec, "price": 10}],
            "buys": [{"item_spec": item_spec, "price": 6}],
        }
    ]
    player["initial_gold"] = 30
    return raw


class TestDeclaredEconomyReachesThePrompt:
    """商人と所持金の宣言が、組み立てたプロンプトに現れる。"""

    def test_initial_gold_becomes_the_players_gold(self, tmp_path: Path) -> None:
        """players[].initial_gold に書いた額が、そのプレイヤーの所持金になる。"""
        path = _write(tmp_path, _world_with_a_merchant_beside(_drill_raw()), "econ.json")

        runtime = create_world_runtime(path)

        status = runtime._player_status_repo.find_by_id(_MORI)
        assert status.gold.value == 30

    def test_gold_defaults_to_zero_when_undeclared(self, tmp_path: Path) -> None:
        """initial_gold を書かないプレイヤーの所持金は 0 のままになる。"""
        raw = _world_with_a_merchant_beside(_drill_raw())
        del raw["players"][0]["initial_gold"]
        path = _write(tmp_path, raw, "econ_no_gold.json")

        runtime = create_world_runtime(path)

        assert runtime._player_status_repo.find_by_id(_MORI).gold.value == 0

    def test_merchant_and_gold_appear_in_the_prompt(self, tmp_path: Path) -> None:
        """商人と同席しているプレイヤーのプロンプトに、品揃え・価格・所持金が出る。"""
        path = _write(tmp_path, _world_with_a_merchant_beside(_drill_raw()), "econ.json")

        prompt = _prompt_of(create_world_runtime(path), _MORI)

        assert '"商人グスタフ"' in prompt
        assert "10G" in prompt
        assert "所持金: 30G" in prompt

    def test_the_prompt_names_items_not_identifiers(self, tmp_path: Path) -> None:
        """品揃えは item_spec の表示名で出て、シナリオの識別子は出ない。"""
        raw = _drill_raw()
        item_spec = raw["item_specs"][0]
        path = _write(tmp_path, _world_with_a_merchant_beside(raw), "econ.json")

        prompt = _prompt_of(create_world_runtime(path), _MORI)

        assert f'"{item_spec["name"]}"' in prompt
        assert item_spec["id"] not in prompt


class TestUndeclaredWorldIsUnchanged:
    """商人を宣言していない世界のプロンプトは、経済の行を 1 つも含まない。"""

    def test_no_merchant_or_gold_line_appears(self, tmp_path: Path) -> None:
        """宣言の無い既存シナリオでは、商人節も所持金行も出ない。"""
        path = _write(tmp_path, _drill_raw(), "plain.json")

        prompt = _prompt_of(create_world_runtime(path), _MORI)

        # 正の対照。プロンプトが空だったり状況確認が組み立たなかったりすると、
        # 「経済の行が無い」は自動的に成立してしまう。常在の節が出ていることを
        # 先に確かめてから、経済の行だけが無いことを見る。
        assert "オブジェクト" in prompt
        assert "商人" not in prompt
        assert "所持金" not in prompt


_TRADE_TOOLS = ("trade_offer", "trade_accept", "trade_decline")


def _tool_names_of(runtime, player_id: PlayerId) -> list:
    """その人にいま出ているツール名の一覧。"""
    client = _PromptCaptureClient()
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
    )
    wiring.run_phase_a(player_id)
    return [tool["function"]["name"] for tool in client.tools]


class TestPlayerTradeIsGatedByItsDeclaration:
    """人同士の取引ツールは、宣言した世界にだけ在る。

    宣言していない既存シナリオに勝手に生えると、そこで想定していない交渉が
    始まり、過去 run との比較が壊れる。逆に宣言したのに出ないのは、シナリオ
    に書いたのに効かない静かな失敗になる。
    """

    def test_the_tools_are_absent_without_the_declaration(self, tmp_path: Path) -> None:
        """宣言の無い世界には、取引の 3 ツールが 1 つも出ない。"""
        path = _write(tmp_path, _drill_raw(), "plain.json")
        runtime = create_world_runtime(path)

        names = _tool_names_of(runtime, _MORI)

        # 正の対照。ツール一覧そのものが空だと「無い」は自動的に成立する。
        assert "wait" in names
        assert [name for name in _TRADE_TOOLS if name in names] == []

    def test_their_names_are_absent_from_the_prompt_too(self, tmp_path: Path) -> None:
        """定義から消すだけでなく、プロンプト本文もその名前を宣伝しない。

        本文が宣伝し続けると、エージェントは存在しないツールを呼ぶ。無効化
        しないより悪い (CLAUDE.md の露出判断)。
        """
        path = _write(tmp_path, _drill_raw(), "plain.json")

        prompt = _prompt_of(create_world_runtime(path), _MORI)

        for name in _TRADE_TOOLS:
            assert name not in prompt

    def test_declaring_it_brings_all_three(self, tmp_path: Path) -> None:
        """`player_trade` を宣言した世界には、3 ツールがそろって出る。"""
        raw = _drill_raw()
        raw["player_trade"] = {"enabled": True}
        path = _write(tmp_path, raw, "trade.json")

        names = _tool_names_of(create_world_runtime(path), _MORI)

        assert [name for name in _TRADE_TOOLS if name in names] == list(_TRADE_TOOLS)

    def test_declaring_it_disabled_keeps_them_away(self, tmp_path: Path) -> None:
        """`enabled: false` と書いた世界では出ない (書いたことが効く)。"""
        raw = _drill_raw()
        raw["player_trade"] = {"enabled": False}
        path = _write(tmp_path, raw, "off.json")

        names = _tool_names_of(create_world_runtime(path), _MORI)

        assert "wait" in names
        assert [name for name in _TRADE_TOOLS if name in names] == []
