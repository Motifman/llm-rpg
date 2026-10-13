"""system prompt とツールの説明が、実在する見出しと、出している引数だけを指すことを保証する。

## 実在しないものを指す文が 4 つ見つかった (#1521)

保存済みの run (`memory_jev_e2e_v4_002`) のプロンプトを読み直すと、次の文が
あった。

- system prompt が「上記【ペルソナ】」を 3 回指すが、シナリオの
  `persona_prompt` を使う経路では【ペルソナ】の見出しが付いていなかった
- `goal_update` の説明が、この toolset に無い `intention` 引数を指していた
- 移動先などの説明が、実在しない節名『現在の状況』を指していた
  (実際の見出しは【現在地と周囲】)

指された側は、それを探すか、無い引数を書く。直したのは文面だが、同じ形の
誤りは文を足すたびに生まれるので、実際に組み立てたプロンプトを読んで
確かめる。

## 何を見ているか

- 【】で書いた節名: system prompt か、続く文面に、その見出しで始まる行がある。
  失敗したときに返す対処文も同じ規則で見る
- 『』で囲んだ名前: プロンプトに見出しか、続く文面の欄の名前 (行頭の
  「接続先:」など) として在るか、節を指していないと宣言したもの (`_QUOTES_THAT_ARE_NOT_PLACES`)
  である。本文のどこかに同じ語があるだけでは足りない。『現在の状況』は
  system prompt の「現在の状況・観測・直近の出来事」という説明文に含まれて
  いたので、語の有無で見ると素通りした
- 引数名: どこかのツールが受け取る引数の名前を書いたら、このターンに渡した
  ツールのどれかがその引数を受け取る。説明を持つツール自身に限らないのは、
  speak の説明が他のツールの say_inline を勧めるように、別のツールの引数を
  指す文が正しく存在するため

## 限界

「」で囲んだ欄の名前 (「所持アイテム」など) は見ていない。「」は台詞や例の
引用にも使うので、節を指しているかを機械では分けられない。旧ワールド用の
ツールの説明と system prompt の雛形 (system_prompt_builder) は、spot graph の
run では渡らないので見ていない。そこには「現在の状況」がまだ残っている。また、この
fixture が作る 1 ターン目の状態でしか見ていないので、条件付きで出る見出し
(【関連する学び】など) を指す文を足すと、ここでは落ちる。そのときは状態を
増やすか、指すのをやめる。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.remediation_mapping import (
    DEFAULT_REMEDIATION_BY_ERROR_CODE,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    get_spot_graph_specs,
)
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    SUBJECTIVE_ACTION_FIELD_PROPERTIES,
    assess_situation_definition,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    resolver_failure_remediation,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"

_SCENARIO_FILES = (
    # persona_prompt を使う経路。【ペルソナ】の見出しが付かなかったのはこちら
    "survival_island_v4_coop.json",
    # persona_prompt を持たず、人物像の組み立て部品が見出し付きの節を作る経路
    "recall_probe_v1.json",
)

#: 『』で囲んでいるが、プロンプトの節や欄を指していない名前。
_QUOTES_THAT_ARE_NOT_PLACES = {
    "環境音": "listen が受け取る音の種類の呼び名",
    '"キー名" が要る': 'interact の操作候補に付く表示 (`"code" が要る`) の形',
}

_HEADING_LINE = re.compile(r"^【([^】]+)】", re.MULTILINE)
_FIELD_LABEL_LINE = re.compile(r"^\s*(?:- )?([^\s:：【「『\"][^:：\n]*)[:：]", re.MULTILINE)
_HEADING_REF = re.compile(r"【([^】]+)】")
_QUOTED = re.compile(r"『([^』]+)』")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class _PromptCaptureClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.tools: list[dict[str, Any]] = []

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        self.messages = messages
        self.tools = tools
        return {"name": "wait", "arguments": {}}


def _descriptions(node: Any) -> list[str]:
    if isinstance(node, dict):
        found: list[str] = []
        for key, value in node.items():
            if key == "description" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_descriptions(value))
        return found
    if isinstance(node, list):
        return [text for item in node for text in _descriptions(item)]
    return []


def _property_names(schema: Any) -> set[str]:
    if isinstance(schema, dict):
        names: set[str] = set()
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                names.update(value)
            names.update(_property_names(value))
        return names
    if isinstance(schema, list):
        return {name for item in schema for name in _property_names(item)}
    return set()


def _argument_names_the_code_knows() -> set[str]:
    """どこかのツールが受け取りうる引数の名前。いま渡しているかは問わない。"""
    names = set(SUBJECTIVE_ACTION_FIELD_PROPERTIES)
    names |= _property_names(assess_situation_definition().parameters)
    for definition, _ in get_spot_graph_specs():
        names |= _property_names(definition.parameters)
    return names


@pytest.fixture(scope="module", params=_SCENARIO_FILES)
def captured(request) -> dict[str, Any]:
    """1 ターン目に渡す文面とツールを取る。"""
    config = ResolvedLlmRuntimeConfig.for_tests(
        episodic_enabled=True,
    )
    runtime = create_world_runtime(_SCENARIOS / request.param, config=config)
    client = _PromptCaptureClient()
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
    )
    wiring.run_phase_a(PlayerId(1))
    system = "\n".join(m["content"] for m in client.messages if m["role"] == "system")
    user = "\n".join(m["content"] for m in client.messages if m["role"] == "user")
    return {
        "system": system,
        "user": user,
        "tools": client.tools,
        "descriptions": _descriptions(client.tools),
    }


def _headings(captured: dict[str, Any]) -> set[str]:
    return set(_HEADING_LINE.findall(captured["system"])) | set(
        _HEADING_LINE.findall(captured["user"])
    )


def _remediation_texts() -> list[str]:
    """失敗したときに返す対処文。共通の対応表と、ツールごとの名前の指定の案内。"""
    texts = list(DEFAULT_REMEDIATION_BY_ERROR_CODE.values())
    for definition, _ in get_spot_graph_specs():
        for error_code in ("INVALID_TARGET_LABEL", "INVALID_ARGUMENT"):
            texts.append(resolver_failure_remediation(definition.name, error_code))
    return texts


class TestPromptPointsOnlyAtWhatExists:
    """実際に組み立てたプロンプトが、実在しない見出し・名前・引数を指さない。"""

    def test_every_section_written_in_brackets_is_a_real_heading(self, captured) -> None:
        """system prompt とツールの説明が【】で指す節は、system prompt か続く文面に、その見出しで始まる行として在る。"""
        headings = _headings(captured)
        referring_texts = [captured["system"], *captured["descriptions"]]

        referred = {name for text in referring_texts for name in _HEADING_REF.findall(text)}
        missing = referred - headings

        assert referred, "【】の参照を 1 つも拾えていない。検査が空振りしている"

        assert missing == set(), f"実在しない見出し: {sorted(missing)} / 実在する見出し: {sorted(headings)}"

    def test_every_quoted_name_is_a_heading_or_field_in_the_prompt(self, captured) -> None:
        """system prompt とツールの説明が『』で囲む名前は、プロンプトに見出しか欄の名前として在るか、節を指していないと宣言したものである。"""
        places = _headings(captured) | {
            label.strip() for label in _FIELD_LABEL_LINE.findall(captured["user"])
        }
        referring_texts = [captured["system"], *captured["descriptions"]]

        quoted = {name for text in referring_texts for name in _QUOTED.findall(text)}
        missing = quoted - places - set(_QUOTES_THAT_ARE_NOT_PLACES)

        assert quoted, "『』の名前を 1 つも拾えていない。検査が空振りしている"

        assert missing == set(), f"プロンプトに見出しも欄も無い名前: {sorted(missing)}"

    def test_every_argument_name_mentioned_is_offered_this_turn(self, captured) -> None:
        """system prompt とツールの説明が引数名を書いたら、このターンに渡したツールのどれかがその引数を受け取る。"""
        offered = _property_names([tool["function"]["parameters"] for tool in captured["tools"]])
        known = _argument_names_the_code_knows()
        referring_texts = [captured["system"], *captured["descriptions"]]

        mentioned = {
            word
            for text in referring_texts
            for word in _IDENTIFIER.findall(text)
            if word in known
        }
        not_offered = mentioned - offered

        assert mentioned, "引数名の参照を 1 つも拾えていない。検査が空振りしている"

        assert not_offered == set(), f"渡していない引数: {sorted(not_offered)}"


    def test_every_section_named_in_failure_remediation_is_a_real_heading(self, captured) -> None:
        """失敗したときに返す対処文が【】で指す節も、system prompt か続く文面に、その見出しで始まる行として在る。"""
        headings = _headings(captured)

        referred = {
            name for text in _remediation_texts() for name in _HEADING_REF.findall(text)
        }
        missing = referred - headings

        assert referred, "【】の参照を 1 つも拾えていない。検査が空振りしている"
        assert missing == set(), f"実在しない見出し: {sorted(missing)}"


def test_every_declared_non_place_quote_is_still_in_use() -> None:
    """節を指していないと宣言した名前は、いまもツールの説明で使われている。使われなくなった宣言は、誤りを素通りさせる穴になる。"""
    descriptions = [
        text
        for definition, _ in get_spot_graph_specs()
        for text in [definition.description, *_descriptions(definition.parameters)]
    ]

    unused = {
        name
        for name in _QUOTES_THAT_ARE_NOT_PLACES
        if not any(f"『{name}』" in text for text in descriptions)
    }

    assert unused == set()
