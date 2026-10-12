"""止めた記憶の部品の欄やツールの名前が、プロンプトのどこにも残らないことを保証する (#1616)。

## 部品を止めても、本文が指し続けていた

`var/runs/mine_v1_007_memo` (エピソードと想起を止めた profile) のシステムプロンプトは、
【関連する記憶】と「能動想起の手段を試す」を指示し続けた。どちらも出ていない。
サヨ T20 は「The instructions mention 能動想起 but no tool」と探し回った。

`tests/demos/test_disabled_tools_vanish_from_the_prompt.py` と同じ形で見張る。
記憶の部品を全部有効にした設定から 1 つずつ止め、システムプロンプト・
1 ターン目の user 文面・ツール定義のどこにも、その部品の名前が出ないことを確かめる。

全部入りの設定は、新しい記憶の profile に、比べた全部入りの run (mine_v1_006、
profile は #1631 で退役) が入れていた古い部品を戻して作る。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.judgment_helpers import ScriptedJudgmentPort

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_ROOT = Path(__file__).resolve().parents[2]
_PROFILES = _ROOT / "data" / "experiment_profiles"
_BEING_MEMORY_PROFILE = "memory_jev_mine_v1_v41_thinking_capped_being_memory"

#: 記憶の部品とは関係の無い差し替え。実 LLM と実 API を呼ばず、型付き判断は
#: 台本どおりに答える代役にする。
_OFFLINE = {
    "LLM_CLIENT": "stub",
    "TYPED_JUDGMENT_PROVIDER": "stub",
    "PROMPT_DATASET_CAPTURE_ENABLED": "false",
    "TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED": "false",
}

#: 新しい記憶の profile が止めていて、全部入りの run が入れていた古い記憶の部品。
#: メモ帳は今のメモの道具と並べられないので止める。
_OLD_MEMORY_PARTS_OF_THE_FULL_RUN = {
    "BELIEF_ATTRIBUTION_ENABLED": "true",
    "BELIEF_CONSOLIDATION_ENABLED": "true",
    "BELIEF_CREATE_GATE_ENABLED": "true",
    "BELIEF_EVIDENCE_ENABLED": "true",
    "EPISODIC_RECALL_ENABLED": "true",
    "ERROR_DRIVEN_REINTERPRETATION_ENABLED": "true",
    "EXPECTATION_SETTLEMENT_ENABLED": "true",
    "GOAL_REFLECT_ENABLED": "true",
    "GOAL_REVISION_ENABLED": "true",
    "GOAL_STAGNATION_EVIDENCE_ENABLED": "true",
    "GOAL_STORE_ENABLED": "true",
    "LLM_AFTERGLOW_ENABLED": "true",
    "LLM_EPISODIC_ENABLED": "true",
    "LLM_EPISODIC_RECALL_HABITUATION_ENABLED": "true",
    "LLM_EPISODIC_RECALL_SLOT_ENABLED": "true",
    "LLM_EPISODIC_SUBJECTIVE_ENABLED": "true",
    "MEMO_TOOLS_ENABLED": "true",
    "PENDING_PREDICTION_ENABLED": "true",
    "PREDICTION_CONTEXT_ID_ENABLED": "true",
    "RECALL_HIT_BOOST_ENABLED": "true",
    "SEMANTIC_LLM_GIST_ENABLED": "true",
    "STAGNATION_PRESSURE_ENABLED": "true",
    "STAGNATION_REASONING_ENABLED": "true",
    "UNCONSCIOUS_CONTEXT_ENABLED": "true",
    "BEING_MEMO_ENABLED": "false",
}

#: 全部入りの run も止めていた能動想起と【関連する学び】も有効にして、全部入りにする。
#: 目次つきのエピソードは設定で止められず、常に入る (#1631)。
_ALL_MEMORY_PARTS = {
    "SEMANTIC_SEARCH_ENABLED": "true",
    "EPISODIC_EXPLORE_RELATED_ENABLED": "true",
    "SEMANTIC_PASSIVE_TOP_K": "3",
}

#: 記憶の部品ごとの、本文に出てはいけない名前。
_RELEVANT_MEMORIES = "関連する記憶"
_ACTIVE_RECALL = "能動想起"
_LEARNED = "関連する学び"
_ACTIVE_MEMOS = "進行中のメモ"
_PENDING_PREDICTIONS = "保留中の予測"
_EXPECTATIONS = "expectations"
_AFTERGLOW = "さっき思い出した記憶の見出し"
_RECALL_EPISODES = "memory_recall_episodes"
_RECALL_BY_HANDLE = "memory_recall_by_handle"
_EXPLORE_RELATED = "memory_explore_related"
_SEARCH_SEMANTIC = "memory_search_semantic"
_MEMO_TOOLS = ("memo_add", "memo_list", "memo_done")
_EPISODE_INDEX = "思い出せる出来事"
_EPISODE_RECALL = "episode_recall"
_EPISODE_REVISE_INDEX = "episode_revise_index"
#: メモの出どころの「エピソードから」。メモ帳を出すときだけ出る。
_MEMO_EPISODE_SOURCE = "episode = 思い出したエピソードから"
#: メモ帳 (#1628) の欄、システムプロンプトの説明、環境の tool の引数。
_MEMO_BOOK = "【メモ】"
_MEMO_RULES = "【メモの書き方】"
_MEMO_ARGUMENT = '"memo": {'
_MEMO_BOOK_NAMES = (_MEMO_BOOK, _MEMO_RULES, _MEMO_ARGUMENT)

_ALL_NAMES = (
    _RELEVANT_MEMORIES,
    _ACTIVE_RECALL,
    _LEARNED,
    _ACTIVE_MEMOS,
    _PENDING_PREDICTIONS,
    _EXPECTATIONS,
    _AFTERGLOW,
    _RECALL_EPISODES,
    _RECALL_BY_HANDLE,
    _EXPLORE_RELATED,
    _SEARCH_SEMANTIC,
    *_MEMO_TOOLS,
    _EPISODE_INDEX,
    _EPISODE_RECALL,
    _EPISODE_REVISE_INDEX,
    *_MEMO_BOOK_NAMES,
    _MEMO_EPISODE_SOURCE,
)

#: 全部入りのとき、1 ターン目のプロンプトに出る名前。
#:
#: **これが正の対照。** 止めたときに「消えること」だけを見ると、もともと出て
#: いなかった名前でも緑になる。【関連する学び】と【保留中の予測】は中身が
#: できてから出る欄で、1 ターン目には出ない。この 2 つの総当たりは、本文が
#: 将来それを指したときに落ちる見張りになる。
#:
#: メモ帳は今のメモの道具と並べられない (設定で止める) ので、全部入りには入らない。
#: メモ帳の名前が全部入りに出ないことが、メモ帳を止めたときの見張りになる。正の対照は
#: ``TestTheMemoBookReplacesTheOldMemo`` が持つ。
#:
#: 予期の引数 ``expectations`` は #1631 で消したので、全部入りでも出ない。名前の表に
#: 残し、どの組み合わせでもプロンプトに戻ってこないことを見張る。
_ADVERTISED_WHEN_ALL_ENABLED = frozenset(_ALL_NAMES) - {
    _LEARNED,
    _PENDING_PREDICTIONS,
    _EXPECTATIONS,
    *_MEMO_BOOK_NAMES,
    _MEMO_EPISODE_SOURCE,
}

#: 全部入りの今のメモを、メモ帳に置き換える差分。
_MEMO_BOOK_INSTEAD = {
    "MEMO_TOOLS_ENABLED": "false",
    "BEING_MEMO_ENABLED": "true",
}

#: (止める部品, 設定の差分, 消えるべき名前)。
_DISABLED_PARTS = [
    pytest.param(
        {"EPISODIC_RECALL_ENABLED": "false"},
        (_RECALL_EPISODES,),
        id="memory_recall_episodes",
    ),
    pytest.param(
        {"SEMANTIC_SEARCH_ENABLED": "false"},
        (_SEARCH_SEMANTIC,),
        id="memory_search_semantic",
    ),
    pytest.param(
        {"EPISODIC_EXPLORE_RELATED_ENABLED": "false"},
        (_EXPLORE_RELATED,),
        id="memory_explore_related",
    ),
    pytest.param(
        # 見出しが無ければ、見出しから引く 2 つのツールも組まれない。
        {"LLM_AFTERGLOW_ENABLED": "false", "EPISODIC_EXPLORE_RELATED_ENABLED": "false"},
        (_AFTERGLOW, _RECALL_BY_HANDLE, _EXPLORE_RELATED),
        id="afterglow",
    ),
    pytest.param(
        {
            "EPISODIC_RECALL_ENABLED": "false",
            "SEMANTIC_SEARCH_ENABLED": "false",
            "EPISODIC_EXPLORE_RELATED_ENABLED": "false",
            "LLM_AFTERGLOW_ENABLED": "false",
        },
        (_ACTIVE_RECALL, _RECALL_EPISODES, _RECALL_BY_HANDLE, _EXPLORE_RELATED, _SEARCH_SEMANTIC),
        id="every_active_recall_tool",
    ),
    pytest.param(
        {"SEMANTIC_PASSIVE_TOP_K": "0"},
        (_LEARNED,),
        id="learned",
    ),
    pytest.param(
        {"MEMO_TOOLS_ENABLED": "false"},
        (_ACTIVE_MEMOS, *_MEMO_TOOLS, *_MEMO_BOOK_NAMES),
        id="memo",
    ),
    pytest.param(
        {"PENDING_PREDICTION_ENABLED": "false"},
        (_PENDING_PREDICTIONS,),
        id="pending_predictions",
    ),
]


class _PromptCaptureClient:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.tools: list[dict] = []

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        self.messages = messages
        self.tools = tools
        return {"name": "wait", "arguments": {}}


def _profile_mapping(profile: str) -> tuple[str, dict[str, str]]:
    raw = json.loads((_PROFILES / f"{profile}.json").read_text(encoding="utf-8"))
    mapping = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in raw["runtime_config"].items()
    }
    return str(_ROOT / raw["scenario"]), mapping


def _first_turn_prompt(scenario: str, mapping: dict[str, str]) -> str:
    """1 ターン目に LLM へ渡すシステムプロンプト・user 文面・ツール定義を 1 つの文字列で返す。"""
    runtime = create_world_runtime(
        scenario, config=ResolvedLlmRuntimeConfig.from_mapping(mapping)
    )
    client = _PromptCaptureClient()
    _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
        typed_judgment_port=ScriptedJudgmentPort(),
    ).run_phase_a(PlayerId(1))
    messages = "\n".join(
        message["content"]
        if isinstance(message["content"], str)
        else json.dumps(message["content"], ensure_ascii=False)
        for message in client.messages
    )
    return messages + "\n" + json.dumps(client.tools, ensure_ascii=False)


def _full_prompt_with(overrides: dict[str, str]) -> str:
    scenario, mapping = _profile_mapping(_BEING_MEMORY_PROFILE)
    return _first_turn_prompt(
        scenario,
        {
            **mapping,
            **_OFFLINE,
            **_OLD_MEMORY_PARTS_OF_THE_FULL_RUN,
            **_ALL_MEMORY_PARTS,
            **overrides,
        },
    )


class TestNoDisabledMemoryPartIsNamedAnywhere:
    """止めた記憶の部品の名前が、1 ターン目のプロンプト全文に出ない。"""

    def test_every_part_is_named_when_all_are_enabled(self) -> None:
        """全部入りの設定では、中身ができてから出る 2 つの欄を除き、どの部品の名前もプロンプトに出る。"""
        prompt = _full_prompt_with({})

        named = {name for name in _ALL_NAMES if name in prompt}

        assert named == _ADVERTISED_WHEN_ALL_ENABLED

    @pytest.mark.parametrize(("overrides", "vanished"), _DISABLED_PARTS)
    def test_the_disabled_part_is_absent(
        self, overrides: dict[str, str], vanished: tuple[str, ...]
    ) -> None:
        """全部入りから 1 つの部品を止めると、その部品の名前がプロンプト全文から消える。"""
        prompt = _full_prompt_with(overrides)

        assert [name for name in vanished if name in prompt] == []

    def test_the_being_memory_profile_names_only_the_memo_book_and_the_index(self) -> None:
        """新しい記憶の profile では、メモ帳と目次つきのエピソードの名前だけが出て、古い記憶の部品の名前はどこにも出ない。"""
        scenario, mapping = _profile_mapping(_BEING_MEMORY_PROFILE)

        prompt = _first_turn_prompt(scenario, {**mapping, **_OFFLINE})

        named = {name for name in _ALL_NAMES if name in prompt}
        assert named == {
            _EPISODE_INDEX,
            _EPISODE_RECALL,
            _EPISODE_REVISE_INDEX,
            *_MEMO_BOOK_NAMES,
            _MEMO_EPISODE_SOURCE,
        }


class TestTheMemoBookReplacesTheOldMemo:
    """全部入りの今のメモをメモ帳に置き換えると、メモ帳の名前だけが出て、今のメモの名前が消えることを保証する (#1628)。"""

    def test_memo_book_names_appear_and_old_memo_names_vanish(self) -> None:
        """メモ帳に置き換えると、【メモ】・【メモの書き方】・引数 memo が出て、【進行中のメモ】と memo_* のツールが消え、ほかの部品の名前は変わらない。"""
        prompt = _full_prompt_with(_MEMO_BOOK_INSTEAD)

        named = {name for name in _ALL_NAMES if name in prompt}

        assert named == (
            _ADVERTISED_WHEN_ALL_ENABLED - {_ACTIVE_MEMOS, *_MEMO_TOOLS}
        ) | {*_MEMO_BOOK_NAMES, _MEMO_EPISODE_SOURCE}
