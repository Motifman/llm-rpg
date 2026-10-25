"""RandomLlmClient が、提示された tool と候補だけからシードに従って行動を選ぶことを保証する。"""

from __future__ import annotations

import random
from typing import Any

from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (
    render_dynamic_argument_candidate_table,
)
from ai_rpg_world.application.llm.services.llm_client_random import (
    RandomLlmClient,
    choose_random_tool_call,
)

_ENTRIES = [
    {"tool": "travel_to", "argument": "destination_label", "values": ["集会所", "倉庫"]},
    {"tool": "interact", "argument": "target_label", "values": ["金庫", "発電機"]},
    {"tool": "interact", "argument": "action_name", "target": "金庫", "values": ["open_safe"]},
    {"tool": "interact", "argument": "action_name", "target": "発電機", "values": ["start_generator", "pour_fuel_can"]},
    {"tool": "give_item", "argument": "gives[].item_label", "values": ["燃料の缶"]},
    {"tool": "give_item", "argument": "gives[].target_player_label", "values": ["ミオ"]},
]


def _tool(name: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_THOUGHT = {"inner_thought": {"type": "string"}}
_TOOLS = [
    _tool("wait", {**_THOUGHT}, ["inner_thought"]),
    _tool(
        "speak",
        {"channel": {"type": "string", "enum": ["say", "shout"]}, "content": {"type": "string"}, **_THOUGHT},
        ["channel", "content", "inner_thought"],
    ),
    _tool("travel_to", {"destination_label": {"type": "string"}, **_THOUGHT}, ["destination_label", "inner_thought"]),
    _tool(
        "interact",
        {
            "target_label": {"type": "string"},
            "action_name": {"type": "string"},
            "parameters": {"type": "object"},
            **_THOUGHT,
        },
        ["target_label", "action_name", "inner_thought"],
    ),
    _tool(
        "give_item",
        {
            "gives": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"item_label": {"type": "string"}, "target_player_label": {"type": "string"}},
                    "required": ["item_label", "target_player_label"],
                },
            },
            **_THOUGHT,
        },
        ["gives", "inner_thought"],
    ),
    _tool("attack", {"target_label": {"type": "string"}, **_THOUGHT}, ["target_label", "inner_thought"]),
    _tool("memo_done", {"memo_ids": {"type": "array", "items": {"type": "string"}}}, ["memo_ids"]),
]


def _messages(entries: list[dict[str, Any]] = _ENTRIES) -> list[dict[str, Any]]:
    table = render_dynamic_argument_candidate_table(entries)
    return [
        {"role": "system", "content": "あなたはハル。"},
        {"role": "user", "content": f"【現在地と周囲】\n...\n\n{table}\n\n行動を 1 つ選んでください。"},
    ]


def _many_choices(seed: int, n: int = 300) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    return [choose_random_tool_call(rng, _messages(), _TOOLS) for _ in range(n)]


class TestSameSeedSameActions:
    """同じシードで同じ順に呼ばれれば、同じ行動の並びになる。"""

    def test_two_clients_with_the_same_seed_return_the_same_sequence(self) -> None:
        """同じシードの 2 つのクライアントに同じ文を 50 回渡すと、返る行動の並びが一致する。"""
        a, b = RandomLlmClient(seed=7), RandomLlmClient(seed=7)

        first = [a.invoke(_messages(), _TOOLS) for _ in range(50)]
        second = [b.invoke(_messages(), _TOOLS) for _ in range(50)]

        assert first == second
        assert a.choices == first

    def test_different_seeds_return_different_sequences(self) -> None:
        """シードを変えると並びが変わる。並びが常に同じなら、上の一致は何も確かめていない。"""
        a, b = RandomLlmClient(seed=7), RandomLlmClient(seed=8)

        first = [a.invoke(_messages(), _TOOLS) for _ in range(50)]
        second = [b.invoke(_messages(), _TOOLS) for _ in range(50)]

        assert first != second


class TestOnlyPresentedCandidates:
    """提示された tool と候補表の値しか選ばない。"""

    def test_named_arguments_come_only_from_the_candidate_table(self) -> None:
        """行き先・対象・渡す品と相手は、候補表に出ている値だけになり、どの値も一度は選ばれる。"""
        calls = _many_choices(seed=1)

        destinations = {c["arguments"]["destination_label"] for c in calls if c["name"] == "travel_to"}
        gives = {
            (g["item_label"], g["target_player_label"])
            for c in calls
            if c["name"] == "give_item"
            for g in c["arguments"]["gives"]
        }

        assert destinations == {"集会所", "倉庫"}
        assert gives == {("燃料の缶", "ミオ")}

    def test_action_name_belongs_to_the_chosen_target(self) -> None:
        """interact の操作名は、選んだ対象の行に出ている操作からだけ選ぶ。"""
        calls = [c for c in _many_choices(seed=2) if c["name"] == "interact"]

        pairs = {(c["arguments"]["target_label"], c["arguments"]["action_name"]) for c in calls}

        assert pairs == {("金庫", "open_safe"), ("発電機", "start_generator"), ("発電機", "pour_fuel_can")}

    def test_tools_whose_named_argument_has_no_candidate_are_never_chosen(self) -> None:
        """候補表に行の無い attack と、ID を要る memo_done は選ばない。でたらめでも実在しない相手は指さない。"""
        names = {c["name"] for c in _many_choices(seed=3)}

        assert names == {"wait", "speak", "travel_to", "interact", "give_item"}

    def test_enum_arguments_come_from_the_tool_definition(self) -> None:
        """speak の channel は、ツール定義の enum に書かれた値だけになる。"""
        channels = {c["arguments"]["channel"] for c in _many_choices(seed=4) if c["name"] == "speak"}

        assert channels == {"say", "shout"}

    def test_without_a_candidate_table_only_tools_without_named_arguments_remain(self) -> None:
        """候補表が無いターンは、名前を指さないツール (待つ・話す) だけから選ぶ。"""
        rng = random.Random(5)
        messages = [{"role": "user", "content": "行動を 1 つ選んでください。"}]

        names = {choose_random_tool_call(rng, messages, _TOOLS)["name"] for _ in range(100)}

        assert names == {"wait", "speak"}

    def test_returns_none_when_no_presented_tool_can_be_called(self) -> None:
        """名前を指すツールしか無く、候補も無いときは、行動を作らず None を返す。"""
        rng = random.Random(6)
        messages = [{"role": "user", "content": "行動を 1 つ選んでください。"}]

        assert choose_random_tool_call(rng, messages, [_TOOLS[2], _TOOLS[5]]) is None
