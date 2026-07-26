"""``scripts/replay_prompt_intervention.py`` のユニットテスト。

記録済み prompt を再送する介入実験で、toolset の差し替えが意図した範囲だけを
変え、集計が「元と同じ tool か」「say_inline を付けたか」を取り違えないことを
保証する。
"""

from __future__ import annotations

import copy

from scripts.replay_prompt_intervention import (
    INTERVENTION_SAY_INLINE_MAX_LENGTH,
    INTERVENTION_TOOLS_GAINING_SAY_INLINE,
    apply_say_inline_intervention,
    _summarise,
)


def _tool(
    name: str,
    *,
    say_inline: bool = False,
    max_length: int = 80,
    description: str = "説明",
    required: list[str] | None = None,
) -> dict:
    properties: dict = {"inner_thought": {"type": "string"}}
    if say_inline:
        properties["say_inline"] = {
            "type": "string",
            "description": "立ち去り際の短い一言",
            "maxLength": max_length,
        }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required if required is not None else ["inner_thought"],
            },
        },
    }


def _props(tools: list[dict], name: str) -> dict:
    for tool in tools:
        if tool["function"]["name"] == name:
            return tool["function"]["parameters"]["properties"]
    raise AssertionError(f"{name} が toolset に無い")


class TestApplySayInlineIntervention:
    """apply_say_inline_intervention が toolset のどこを変え、どこを変えないかを保証する。"""

    def test_raises_the_cap_on_tools_that_already_have_say_inline(self) -> None:
        """既に say_inline を持つツールの maxLength を介入値へ引き上げる。"""
        out = apply_say_inline_intervention([_tool("travel_to", say_inline=True)])
        assert _props(out, "travel_to")["say_inline"]["maxLength"] == (
            INTERVENTION_SAY_INLINE_MAX_LENGTH
        )

    def test_cap_is_high_enough_to_hold_a_typical_utterance(self) -> None:
        """実測の speak 本文は中央値 104 字なので、介入値はそれを超えている
        (80 字のままでは 71% が入らないのが介入の理由)。"""
        assert INTERVENTION_SAY_INLINE_MAX_LENGTH > 104

    def test_replaces_the_description_that_redirected_to_the_speak_tool(self) -> None:
        """現行文の「立ち去り際」誘導を消し、ふだんの共有はここに書くと伝える。"""
        out = apply_say_inline_intervention([_tool("interact", say_inline=True)])
        description = _props(out, "interact")["say_inline"]["description"]
        assert "立ち去り際" not in description
        assert "基本" in description

    def test_adds_say_inline_to_wait_and_explore(self) -> None:
        """say_inline を持たなかった wait / explore に足す。wait が無いと
        「その場に留まって喋る」がどのツールでも表現できない。"""
        out = apply_say_inline_intervention([_tool("wait"), _tool("explore")])
        for name in INTERVENTION_TOOLS_GAINING_SAY_INLINE:
            assert "say_inline" in _props(out, name)

    def test_say_inline_stays_optional(self) -> None:
        """say_inline を required に入れない。必須にすると黙って動く選択を潰す。"""
        out = apply_say_inline_intervention([_tool("wait"), _tool("interact", say_inline=True)])
        for tool in out:
            assert "say_inline" not in tool["function"]["parameters"]["required"]

    def test_extends_the_speak_description_without_dropping_the_original(self) -> None:
        """speak の説明は消さずに追記する。shout / whisper / 長話の役割は残す。"""
        out = apply_say_inline_intervention([_tool("speak", description="元の説明")])
        description = out[0]["function"]["description"]
        assert description.startswith("元の説明")
        assert "whisper" in description

    def test_does_not_add_say_inline_to_unrelated_tools(self) -> None:
        """対象外のツール (memo_add 等) には say_inline を足さない。"""
        out = apply_say_inline_intervention([_tool("memo_add")])
        assert "say_inline" not in _props(out, "memo_add")

    def test_does_not_mutate_the_input_toolset(self) -> None:
        """アーム A が同じ toolset を使い回すため、入力を書き換えない。"""
        original = [_tool("travel_to", say_inline=True), _tool("speak")]
        snapshot = copy.deepcopy(original)
        apply_say_inline_intervention(original)
        assert original == snapshot

    def test_tool_without_parameters_is_passed_through(self) -> None:
        """parameters を持たない形の要素でも例外にせずそのまま通す。"""
        out = apply_say_inline_intervention([{"type": "function", "function": {"name": "x"}}])
        assert out[0]["function"]["name"] == "x"

    def test_non_function_entry_is_passed_through(self) -> None:
        """function を持たない要素も落とさずに通す (件数が黙って減らない)。"""
        out = apply_say_inline_intervention([{"type": "other"}])
        assert out == [{"type": "other"}]


class TestSummarise:
    """_summarise がアームごとの再現率と say_inline 付与率を正しく数える挙動を保証する。"""

    def test_same_tool_rate_counts_only_answered_calls(self) -> None:
        """失敗した呼び出しは分母から外す。エラーを「別の tool を選んだ」と
        混ぜると再現率が実際より低く出る。"""
        rows = [
            {"arm": "A", "recorded_tool": "speak", "tool": "speak", "arguments": {}},
            {"arm": "A", "recorded_tool": "speak", "tool": None, "error": "timeout"},
        ]
        summary = _summarise(rows)["A"]
        assert summary["answered"] == 1
        assert summary["errors"] == 1
        assert summary["same_tool_rate"] == 1.0

    def test_say_inline_attach_rate_excludes_speak(self) -> None:
        """say_inline 付与率の分母は speak 以外の行動。speak を含めると
        「行動しながら喋った」の率が薄まる。"""
        rows = [
            {"arm": "B", "recorded_tool": "speak", "tool": "speak", "arguments": {}},
            {
                "arm": "B",
                "recorded_tool": "speak",
                "tool": "explore",
                "arguments": {"say_inline": "見つけた"},
            },
            {"arm": "B", "recorded_tool": "speak", "tool": "travel_to", "arguments": {}},
        ]
        summary = _summarise(rows)["B"]
        assert summary["non_speak_actions"] == 2
        assert summary["non_speak_with_say_inline"] == 1
        assert summary["say_inline_attach_rate"] == 0.5

    def test_empty_say_inline_string_does_not_count_as_attached(self) -> None:
        """空文字の say_inline は「発話しない」なので付与に数えない。"""
        rows = [
            {"arm": "B", "recorded_tool": "speak", "tool": "explore", "arguments": {"say_inline": ""}},
        ]
        assert _summarise(rows)["B"]["non_speak_with_say_inline"] == 0

    def test_arms_are_summarised_separately(self) -> None:
        """A と B を混ぜずに別集計する (混ぜると介入差が消える)。"""
        rows = [
            {"arm": "A", "recorded_tool": "speak", "tool": "speak", "arguments": {}},
            {"arm": "B", "recorded_tool": "speak", "tool": "explore", "arguments": {}},
        ]
        summary = _summarise(rows)
        assert summary["A"]["chose_speak"] == 1
        assert summary["B"]["chose_speak"] == 0

    def test_rates_are_none_when_there_is_nothing_to_divide_by(self) -> None:
        """全件失敗した run では率を 0 と書かず None にする (0% と区別する)。"""
        rows = [{"arm": "A", "recorded_tool": "speak", "tool": None, "error": "boom"}]
        summary = _summarise(rows)["A"]
        assert summary["same_tool_rate"] is None
        assert summary["say_inline_attach_rate"] is None
