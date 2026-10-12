"""profile で目次を出す設定にした世界の runtime が、【思い出せる出来事】を毎ターン出し、呼び出しのツールで本文を返すことを保証する (#1623)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_EPISODE_RECALL,
    TOOL_NAME_EPISODE_REVISE_INDEX,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from tests.application.being.expectation.support import ScriptedJudgmentPort

_ISLAND = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "survival_island_v4_coop.json"
_HEADING = "【思い出せる出来事】"


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        self.events: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, player_id, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


class _PromptCaptureClient:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.tools: list[dict] = []

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        self.messages = messages
        self.tools = tools
        return {"name": "wait", "arguments": {}}


def _runtime(order: str | None, **extra: str):
    values = {
        "SHORT_TERM_MEMORY_KIND": "rolling_summary",
        "BEING_EPISODE_WRITING_ENABLED": "1",
        "TYPED_JUDGMENT_PROVIDER": "stub",
        **extra,
    }
    if order is not None:
        values["BEING_EPISODE_INDEX_ORDER"] = order
    runtime = create_world_runtime(_ISLAND, config=ResolvedLlmRuntimeConfig.from_mapping(values=values))
    recorder = _Recorder()
    runtime.set_trace_recorder(recorder)
    return runtime, recorder


def _being_of(runtime, pid):
    runtime._acting_being_for(pid)
    return runtime.aux_being_resolver.resolve_being_id(runtime.aux_being_default_world_id, pid)


def _write(runtime, pid, number: int, *, summary: str, written_turn: int = 0, environment_name: str | None = None) -> Episode:
    being_id = _being_of(runtime, pid)
    store = runtime._being_episode_store
    episode = Episode.write(
        episode_id=f"{number:06x}00-0000-4000-8000-000000000000",
        environment_name=environment_name or runtime.scenario.metadata.title,
        written_turn=written_turn,
        index=EpisodeIndex(summary=summary, recall_when="火の話が出たとき"),
        body=f"{summary}ときの本文。",
        taken_handles={e.handle for e in store.list_by_being(being_id)},
    )
    store.add(being_id, episode)
    return episode


def _first_turn(runtime, pid: PlayerId) -> tuple[str, str, list[dict]]:
    """(システムプロンプト, user 文面, ツール定義) を返す。"""
    client = _PromptCaptureClient()
    _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=client,
        typed_judgment_port=ScriptedJudgmentPort(),
    ).run_phase_a(pid)
    system, user = (m["content"] for m in client.messages)
    return system, user, client.tools


def _section(user: str) -> list[str]:
    lines = user.splitlines()
    start = lines.index(_HEADING) + 1
    end = lines.index("", start)
    return lines[start:end]


def _tool_names(tools: list[dict]) -> set[str]:
    return {t["function"]["name"] for t in tools}


class TestTheIndexInThePrompt:
    """目次の区画が、設定した並べ方と件数で 1 ターン目から user 文面に出ることを保証する。"""

    def test_the_index_is_shown_empty_before_any_episode(self) -> None:
        """エピソードがまだ無くても、【思い出せる出来事】の欄は出て「まだ無い」と書く。"""
        runtime, _ = _runtime("recalled_rises_to_top")
        pid = runtime.get_player_ids()[0]

        _, user, _ = _first_turn(runtime, pid)

        assert _section(user) == ["(まだ無い)"]

    def test_only_n_newest_episodes_are_listed_newest_first(self) -> None:
        """新しい順で N=2 にすると、書いた時の新しい 2 件だけが新しい順に並ぶ。"""
        runtime, _ = _runtime("newest_first", BEING_EPISODE_INDEX_LIMIT="2")
        pid = runtime.get_player_ids()[0]
        _write(runtime, pid, 1, summary="浜に流れ着いた", written_turn=0)
        newer = _write(runtime, pid, 2, summary="火を起こした", written_turn=2)
        middle = _write(runtime, pid, 3, summary="小屋を建てた", written_turn=1)

        _, user, _ = _first_turn(runtime, pid)

        assert [line.split("]")[0] for line in _section(user)] == [f"[{newer.handle}", f"[{middle.handle}"]

    def test_a_recalled_episode_rises_to_the_top(self) -> None:
        """呼び出されたら上に積み直す並べ方では、古くても最近呼び出したエピソードが先頭に来る。"""
        runtime, _ = _runtime("recalled_rises_to_top")
        pid = runtime.get_player_ids()[0]
        old = _write(runtime, pid, 1, summary="浜に流れ着いた", written_turn=0)
        _write(runtime, pid, 2, summary="火を起こした", written_turn=1)
        runtime._memory_turn_clock.advance_turn(_being_of(runtime, pid))
        runtime._memory_turn_clock.advance_turn(_being_of(runtime, pid))
        runtime.run_llm_auxiliary_tool(pid, TOOL_NAME_EPISODE_RECALL, {"handles": [old.handle]})

        _, user, _ = _first_turn(runtime, pid)

        assert _section(user)[0].startswith(f"[{old.handle}] 浜に流れ着いた")
        assert _section(user)[0].endswith("(呼び出し 1 回)")

    def test_newest_first_does_not_lift_a_recalled_episode(self) -> None:
        """新しい順を選ぶと、古いエピソードを呼び出しても先頭には来ず、書いた時の順のまま並ぶ。"""
        runtime, _ = _runtime("newest_first")
        pid = runtime.get_player_ids()[0]
        old = _write(runtime, pid, 1, summary="浜に流れ着いた", written_turn=0)
        newer = _write(runtime, pid, 2, summary="火を起こした", written_turn=1)
        runtime._memory_turn_clock.advance_turn(_being_of(runtime, pid))
        runtime._memory_turn_clock.advance_turn(_being_of(runtime, pid))
        runtime.run_llm_auxiliary_tool(pid, TOOL_NAME_EPISODE_RECALL, {"handles": [old.handle]})

        _, user, _ = _first_turn(runtime, pid)

        assert [line.split("]")[0] for line in _section(user)] == [f"[{newer.handle}", f"[{old.handle}"]

    def test_the_index_comes_after_the_recent_events(self) -> None:
        """毎ターン伸びる【直近の出来事】より後ろに置き、その先頭のキャッシュを崩さない。"""
        runtime, _ = _runtime("recalled_rises_to_top")
        pid = runtime.get_player_ids()[0]

        _, user, _ = _first_turn(runtime, pid)

        assert user.index("【直近の出来事】") < user.index(_HEADING) < user.index("【現在地と周囲】")

    def test_showing_the_index_is_traced_with_the_handles(self) -> None:
        """目次を出すたびに、並べ方・N・記録の件数・出した呼び名を trace に 1 件残す。"""
        runtime, recorder = _runtime("newest_first", BEING_EPISODE_INDEX_LIMIT="1")
        pid = runtime.get_player_ids()[0]
        _write(runtime, pid, 1, summary="浜に流れ着いた", written_turn=0)
        newer = _write(runtime, pid, 2, summary="火を起こした", written_turn=1)

        _first_turn(runtime, pid)

        [payload] = [p for k, _, p in recorder.events if k == TraceEventKind.EPISODE_INDEX_SHOWN]
        assert payload == {
            "being_id": _being_of(runtime, pid).value,
            "order": "newest_first",
            "limit": 1,
            "total_count": 2,
            "shown_handles": [newer.handle],
        }

    def test_the_system_prompt_explains_the_index_and_the_tool(self) -> None:
        """システムプロンプトが、【思い出せる出来事】は目次で、本文は呼び出しのツールで読むと書く。"""
        runtime, _ = _runtime("recalled_rises_to_top")
        pid = runtime.get_player_ids()[0]

        system, _, _ = _first_turn(runtime, pid)

        assert _HEADING in system
        assert TOOL_NAME_EPISODE_RECALL in system


class TestTheRecallTool:
    """呼び出しのツールが目次を出す設定で上限 M 件とともに出て、手番を経由せず runtime から直接呼び出しても本文を返すことを保証する。"""

    def test_the_tool_is_offered_with_the_configured_limit(self) -> None:
        """目次を出す設定では呼び出しのツールが出て、呼び名の上限が M 件になる。"""
        runtime, _ = _runtime("recalled_rises_to_top", BEING_EPISODE_RECALL_MAX_HANDLES="2")
        pid = runtime.get_player_ids()[0]

        _, _, tools = _first_turn(runtime, pid)

        [recall] = [t for t in tools if t["function"]["name"] == TOOL_NAME_EPISODE_RECALL]
        assert recall["function"]["parameters"]["properties"]["handles"]["maxItems"] == 2

    def test_recalling_through_the_runtime_returns_the_body_and_traces(self) -> None:
        """runtime から呼び出すと本文が返り、回数が増え、呼び出しの trace が残る。"""
        runtime, recorder = _runtime("recalled_rises_to_top")
        pid = runtime.get_player_ids()[0]
        episode = _write(runtime, pid, 1, summary="火を起こした")

        result = runtime.run_llm_auxiliary_tool(pid, TOOL_NAME_EPISODE_RECALL, {"handles": [episode.handle]})

        assert result.success is True
        assert "火を起こしたときの本文。" in result.message
        stored = runtime._being_episode_store.find_by_handle(_being_of(runtime, pid), episode.handle)
        assert stored is not None and stored.recall_count == 1
        assert [p["outcome"] for k, _, p in recorder.events if k == TraceEventKind.EPISODE_RECALL] == ["recalled"]


class _RecallClient(_PromptCaptureClient):
    def __init__(self, handles: list[str]) -> None:
        super().__init__()
        self.handles = handles

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        super().invoke(messages, tools, tool_choice, **kwargs)
        return {"name": TOOL_NAME_EPISODE_RECALL, "arguments": {"handles": self.handles}}


class TestRecallingInATurn:
    """エージェントが手番で呼び出しのツールを選ぶと、1 手の経路を通って本文が返ることを保証する。"""

    def test_a_turn_that_chooses_the_tool_recalls_the_episode(self) -> None:
        """LLM が手番で呼び出しのツールを選ぶと、成功の結果に本文が載り、回数が増える。"""
        runtime, _ = _runtime("recalled_rises_to_top")
        pid = runtime.get_player_ids()[0]
        episode = _write(runtime, pid, 1, summary="火を起こした")

        result = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=_RecallClient([episode.handle]),
            typed_judgment_port=ScriptedJudgmentPort(),
        ).run_turn(pid)

        assert result.success is True
        assert "火を起こしたときの本文。" in result.message
        stored = runtime._being_episode_store.find_by_handle(_being_of(runtime, pid), episode.handle)
        assert stored is not None and stored.recall_count == 1


class _ScriptedClient(_PromptCaptureClient):
    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        super().__init__()
        self.name = name
        self.arguments = arguments

    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        super().invoke(messages, tools, tool_choice, **kwargs)
        return {"name": self.name, "arguments": self.arguments}


def _turn(runtime, pid: PlayerId, name: str, arguments: dict[str, Any]):
    return _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=_ScriptedClient(name, arguments),
        typed_judgment_port=ScriptedJudgmentPort(),
    ).run_turn(pid)


class TestRevisingTheIndexInATurn:
    """目次を直すツールが目次を出す設定で出て、手番で選ぶと次の目次に直した文が出ることを保証する。"""

    def test_the_revision_tool_is_offered_with_the_index(self) -> None:
        """目次を出す設定では、呼び出しのツールと並んで目次を直すツールが出る。"""
        runtime, _ = _runtime("recalled_rises_to_top")
        pid = runtime.get_player_ids()[0]

        _, _, tools = _first_turn(runtime, pid)

        assert {TOOL_NAME_EPISODE_RECALL, TOOL_NAME_EPISODE_REVISE_INDEX} <= _tool_names(tools)

    def test_a_revised_index_shows_in_the_next_prompt(self) -> None:
        """手番で目次を直すと、次のプロンプトの【思い出せる出来事】にその行が直した文で出る。"""
        runtime, recorder = _runtime("recalled_rises_to_top")
        pid = runtime.get_player_ids()[0]
        episode = _write(runtime, pid, 1, summary="火を起こした")

        result = _turn(
            runtime,
            pid,
            TOOL_NAME_EPISODE_REVISE_INDEX,
            {"handle": episode.handle, "about": "湿った流木で火を起こした", "recall_when": "雨の日に火が要るとき"},
        )
        _, user, _ = _first_turn(runtime, pid)

        assert result.success is True
        assert _section(user)[0].startswith(
            f"[{episode.handle}] 湿った流木で火を起こした — 思い出すとき: 雨の日に火が要るとき"
        )
        revisions = [p for k, _, p in recorder.events if k == TraceEventKind.EPISODE_INDEX_REVISION]
        assert [p["before"]["about"] for p in revisions] == ["火を起こした"]


_MEMO_BOOK = {"BEING_MEMO_ENABLED": "1", "MEMO_TOOLS_ENABLED": "false", "MEMO_DISTILL_ENABLED": "false"}


class TestMemoFromAnEpisode:
    """目次を出す設定では、メモの「分かったこと」の出どころにエピソードの呼び名を選べることを保証する。"""

    def test_the_memo_argument_offers_the_episode_source_with_the_index(self) -> None:
        """目次とメモ帳の両方を出す設定では、引数 memo の出どころの選択肢に episode が入る。"""
        runtime, _ = _runtime("recalled_rises_to_top", **_MEMO_BOOK)
        pid = runtime.get_player_ids()[0]

        _, _, tools = _first_turn(runtime, pid)

        assert "episode = 思い出したエピソードから" in json.dumps(tools, ensure_ascii=False)

    def test_the_memo_argument_does_not_offer_it_without_the_index(self) -> None:
        """メモ帳だけを出し目次を出さない設定では、出どころの選択肢に episode が入らない。"""
        runtime, _ = _runtime(None, **_MEMO_BOOK)
        pid = runtime.get_player_ids()[0]

        _, _, tools = _first_turn(runtime, pid)

        assert "episode = 思い出したエピソードから" not in json.dumps(tools, ensure_ascii=False)

    def test_a_fact_from_an_episode_is_written_with_its_handle(self) -> None:
        """行動に添えた memo で、出どころをエピソードにして呼び名を書くと、その呼び名つきの「分かったこと」が入る。"""
        runtime, _ = _runtime("recalled_rises_to_top", **_MEMO_BOOK)
        pid = runtime.get_player_ids()[0]
        episode = _write(runtime, pid, 1, summary="火を起こした")

        _turn(
            runtime,
            pid,
            "wait",
            {
                "memo": [
                    {
                        "do": "add",
                        "kind": "fact",
                        "text": "湿った流木は火が付きにくい",
                        "source": "episode",
                        "certainty": "sure",
                        "from": episode.handle,
                    }
                ]
            },
        )

        [memo] = runtime._being_memo_store.get(_being_of(runtime, pid)).memos
        assert memo.provenance is not None
        assert memo.provenance.source_from == episode.handle

    def test_an_episode_that_sank_out_of_the_index_is_still_accepted(self) -> None:
        """目次の件数から外れた (沈んだ) エピソードの呼び名でも、その Being の記録にあれば出どころとして受け付ける。"""
        runtime, _ = _runtime("newest_first", BEING_EPISODE_INDEX_LIMIT="1", **_MEMO_BOOK)
        pid = runtime.get_player_ids()[0]
        sunk = _write(runtime, pid, 1, summary="浜に流れ着いた", written_turn=0)
        _write(runtime, pid, 2, summary="火を起こした", written_turn=1)

        _turn(
            runtime,
            pid,
            "wait",
            {
                "memo": [
                    {
                        "do": "add",
                        "kind": "fact",
                        "text": "浜は北に続いている",
                        "source": "episode",
                        "certainty": "guess",
                        "from": sunk.handle,
                    }
                ]
            },
        )

        [memo] = runtime._being_memo_store.get(_being_of(runtime, pid)).memos
        assert memo.provenance is not None and memo.provenance.source_from == sunk.handle


class TestTheDisabledProfile:
    """目次を出さない設定 (既定) では、区画もツールもシステムプロンプトの説明も出ないことを保証する。"""

    @pytest.mark.parametrize("order", [None, "off"])
    def test_nothing_about_the_index_appears(self, order: str | None) -> None:
        """並べ方を書かないか off にすると、【思い出せる出来事】も呼び出しのツールもプロンプト全文に出ない。"""
        runtime, recorder = _runtime(order)
        pid = runtime.get_player_ids()[0]
        _write(runtime, pid, 1, summary="火を起こした")

        system, user, tools = _first_turn(runtime, pid)

        whole = system + user + json.dumps(tools, ensure_ascii=False)
        assert _HEADING not in whole
        assert TOOL_NAME_EPISODE_RECALL not in whole
        assert TOOL_NAME_EPISODE_REVISE_INDEX not in whole
        assert [k for k, _, _ in recorder.events if k == TraceEventKind.EPISODE_INDEX_SHOWN] == []
